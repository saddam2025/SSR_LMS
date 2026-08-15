"""Authentication domain services extracted in V68.

Keeps session establishment, OTP delivery, and phone normalization independent
from the HTTP router and app.main.
"""
import os, re, secrets
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import engine
from ..models import ActiveSession, Device, OTPChallenge, User
from ..request_context import DEVICE_COOKIE_NAME, IS_PRODUCTION, audit, client_ip, template_context
from ..security import (
    MAX_DEVICES, STUDENT_SINGLE_SESSION, create_session_token, device_fingerprint,
    ensure_csrf, session_absolute_expiry, session_idle_deadline, sha256,
)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("20") and len(digits) == 12:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    return digits[:15]


def _safe_outbound_webhook_url(value: str) -> str:
    clean = value.strip()
    if not clean:
        return ""
    parsed = urlparse(clean)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid webhook URL")
    if IS_PRODUCTION and parsed.scheme != "https":
        raise ValueError("production webhook URL must use HTTPS")
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("unsupported webhook URL scheme")
    return clean


def _send_otp(phone: str, code: str):
    raw_url = os.getenv("OTP_SMS_WEBHOOK_URL", "").strip()
    if not raw_url:
        if IS_PRODUCTION:
            raise HTTPException(503, "خدمة الرسائل القصيرة غير مهيأة")
        return
    try:
        url = _safe_outbound_webhook_url(raw_url)
    except ValueError:
        raise HTTPException(503, "إعداد خدمة الرسائل غير آمن")
    headers = {"Content-Type": "application/json"}
    token = os.getenv("OTP_SMS_WEBHOOK_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = httpx.post(url, json={"phone": phone, "code": code, "message": f"رمز دخول المستشار: {code}"}, headers=headers, timeout=10)
        r.raise_for_status()
    except Exception:
        raise HTTPException(503, "تعذر إرسال رمز التحقق حاليًا")


def create_otp(db: Session, user: User, phone: str, purpose: str = "login") -> str:
    now = datetime.utcnow()
    db.query(OTPChallenge).filter(
        OTPChallenge.user_id == user.id,
        OTPChallenge.purpose == purpose,
        OTPChallenge.used_at.is_(None),
    ).update({OTPChallenge.used_at: now}, synchronize_session=False)
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = OTPChallenge(
        user_id=user.id, phone=phone, code_hash=sha256(code), purpose=purpose,
        expires_at=now + timedelta(minutes=5),
    )
    db.add(challenge)
    db.commit()
    try:
        _send_otp(phone, code)
    except Exception:
        challenge.used_at = datetime.utcnow()
        db.commit()
        raise
    return code


def _pg_xact_lock(db: Session, namespace: int, entity_id: int):
    if engine.dialect.name == "postgresql":
        safe_entity = int(entity_id) & 0x7FFFFFFF
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :entity)"), {"ns": int(namespace), "entity": safe_entity})


def establish_session(request: Request, db: Session, u: User, render_login):
    """Create the authenticated session and enforce device/session policy.

    render_login is injected by the router so this service does not depend on
    Jinja/template configuration.
    """
    now = datetime.utcnow()
    _pg_xact_lock(db, 5501, u.id)
    ua = request.headers.get("user-agent", "")[:300]
    lang = request.headers.get("accept-language", "")[:80]
    device_token = request.cookies.get(DEVICE_COOKIE_NAME, "") or secrets.token_urlsafe(32)
    fp = device_fingerprint(ua, lang, device_token)
    device = db.query(Device).filter_by(user_id=u.id, fingerprint_hash=fp).first()
    if not device:
        device_count = db.query(Device).filter_by(user_id=u.id, blocked=False).count()
        if u.role == "student" and device_count >= MAX_DEVICES:
            audit(db, request, u, "device_limit_blocked", {"max_devices": MAX_DEVICES})
            return render_login(template_context(request, db, error=f"تم الوصول للحد الأقصى للأجهزة ({MAX_DEVICES}). تواصل مع الإدارة لإزالة جهاز."), 403)
        device = Device(user_id=u.id, fingerprint_hash=fp, label=ua[:180] or "Browser", last_ip=client_ip(request))
        db.add(device)
        db.flush()
        audit(db, request, u, "new_device_registered", {"device_id": device.id}, commit=False)
    if device.blocked:
        audit(db, request, u, "blocked_device_login_attempt", {"device_id": device.id})
        return render_login(template_context(request, db, error="هذا الجهاز محظور. تواصل مع الإدارة."), 403)
    device.last_ip = client_ip(request)
    device.last_seen_at = now

    if u.role == "student" and STUDENT_SINGLE_SESSION:
        active_sessions = db.query(ActiveSession).filter(
            ActiveSession.user_id == u.id, ActiveSession.revoked_at.is_(None)
        ).all()
        revoked_ids = []
        for old_session in active_sessions:
            old_session.revoked_at = now
            revoked_ids.append(old_session.id)
        if revoked_ids:
            audit(db, request, u, "student_previous_sessions_revoked", {"session_ids": revoked_ids, "reason": "new_login"}, commit=False)

    raw_sid, sid_hash = create_session_token()
    rec = ActiveSession(
        user_id=u.id, device_id=device.id, token_hash=sid_hash, ip=client_ip(request),
        user_agent=ua, absolute_expires_at=session_absolute_expiry(),
    )
    db.add(rec)
    db.commit()
    request.session.clear()
    request.session["sid"] = raw_sid
    ensure_csrf(request.session)
    audit(db, request, u, "login", {"session_id": rec.id, "device_id": device.id})

    staff_landing = {
        "super_admin": "/admin", "admin": "/admin", "content_manager": "/teacher",
        "support": "/support", "accounting": "/admin/commerce",
    }
    frontend_origin = os.getenv("FRONTEND_PRIMARY_ORIGIN", "").strip().rstrip("/")
    allowed_frontends = [x.strip().rstrip("/") for x in os.getenv("FRONTEND_ORIGINS", "").split(",") if x.strip()]
    if frontend_origin and frontend_origin not in allowed_frontends:
        frontend_origin = ""
    if u.role in staff_landing:
        response = RedirectResponse(staff_landing[u.role], 303)
    elif u.role == "parent":
        response = RedirectResponse(f"{frontend_origin}/parent/" if frontend_origin else "/parent", 303)
    else:
        response = RedirectResponse(f"{frontend_origin}/student/" if frontend_origin else "/dashboard", 303)
    response.set_cookie(
        DEVICE_COOKIE_NAME, device_token, max_age=365 * 24 * 3600, httponly=True,
        secure=IS_PRODUCTION, samesite="lax", path="/",
    )
    return response
