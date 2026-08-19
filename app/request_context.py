"""Shared authentication/request context/audit primitives.

V66 extracts these cross-cutting concerns from main.py so routers/services can
reuse them without importing the application module.
"""
import json, os, secrets
import ipaddress
from datetime import datetime
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session
from .models import ActiveSession, AuditLog, Device, Notification, User
from .cache import get_json as cache_get_json, set_json as cache_set_json
from .permissions import ROLE_LABELS, STAFF_ROLES
from .security import (
    REQUIRE_STAFF_MFA, device_fingerprint, ensure_csrf, session_idle_deadline,
    sha256,
)

IS_PRODUCTION = os.getenv("ENV") == "production"
DEVICE_COOKIE_NAME = "__Host-lms_device" if IS_PRODUCTION else "lms_device"
SESSION_TOUCH_SECONDS = max(15, min(int(os.getenv("SESSION_TOUCH_SECONDS", "180")), 300))


def _validated_ip(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    # Strip RFC 7239-ish brackets for IPv6 only; proxy headers used here should
    # otherwise contain bare addresses. Never persist attacker-controlled text as IP.
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return ""


def client_ip(request: Request) -> str:
    if os.getenv("TRUST_PROXY_HEADERS", "false").lower() == "true":
        # In the supported production topology Cloudflare sits in front of Railway.
        # Cloudflare preserves the end-user address in CF-Connecting-IP, while
        # Railway's X-Real-IP can otherwise represent the CDN/proxy hop.
        if os.getenv("CLOUDFLARE_DEPLOYMENT", "false").lower() in {"1", "true", "yes", "on"}:
            cf_ip = _validated_ip(request.headers.get("cf-connecting-ip") or "")
            if cf_ip:
                return cf_ip
        real = _validated_ip(request.headers.get("x-real-ip") or "")
        if real:
            return real
        forwarded = _validated_ip((request.headers.get("x-forwarded-for") or "").split(",", 1)[0])
        if forwarded:
            return forwarded
    return (request.client.host if request.client else "")[:80]


def session_record(request: Request, db: Session):
    if hasattr(request.state, "_lms_session_record_resolved"):
        return getattr(request.state, "_lms_session_record", None)
    request.state._lms_session_record_resolved = True
    request.state._lms_session_record = None
    raw = request.session.get("sid")
    if not raw:
        return None
    rec = db.query(ActiveSession).filter(ActiveSession.token_hash == sha256(raw)).first()
    if not rec or rec.revoked_at:
        request.session.clear(); return None
    now = datetime.utcnow()
    if rec.absolute_expires_at <= now or session_idle_deadline(rec.last_seen_at) <= now:
        rec.revoked_at = now; db.commit(); request.session.clear(); return None
    device = None
    if rec.device_id:
        device = db.get(Device, rec.device_id)
        if not device or device.blocked:
            rec.revoked_at = now; db.commit(); request.session.clear(); return None
        device_token = request.cookies.get(DEVICE_COOKIE_NAME, "")
        if not device_token:
            rec.revoked_at = now; db.commit(); request.session.clear(); return None
        current_fp = device_fingerprint(request.headers.get("user-agent", "")[:300], request.headers.get("accept-language", "")[:80], device_token)
        if not secrets.compare_digest(device.fingerprint_hash, current_fp):
            rec.revoked_at = now; db.commit(); request.session.clear(); return None
    last_seen = rec.last_seen_at or now
    if (now - last_seen).total_seconds() >= SESSION_TOUCH_SECONDS:
        rec.last_seen_at = now
        if device is not None:
            device.last_ip = client_ip(request); device.last_seen_at = now
        db.commit()
    request.state._lms_session_record = rec
    return rec


def current_user(request: Request, db: Session):
    if hasattr(request.state, "_lms_current_user_resolved"):
        return getattr(request.state, "_lms_current_user", None)
    request.state._lms_current_user_resolved = True
    request.state._lms_current_user = None
    rec = session_record(request, db)
    if not rec: return None
    u = db.get(User, rec.user_id)
    if not u or not u.is_active:
        if rec and not rec.revoked_at:
            rec.revoked_at = datetime.utcnow(); db.commit()
        request.session.clear(); request.state._lms_session_record = None; return None
    request.state._lms_current_user = u
    return u


def require_user(request: Request, db: Session):
    u = current_user(request, db)
    if not u: raise HTTPException(status_code=401, detail="auth_required")
    return u


def require_role(request: Request, db: Session, *roles):
    u = require_user(request, db)
    if u.role != "super_admin" and u.role not in roles:
        raise HTTPException(status_code=403, detail="role_forbidden")
    if REQUIRE_STAFF_MFA and u.role in STAFF_ROLES and not u.mfa_enabled:
        raise HTTPException(status_code=428, detail="يلزم تفعيل المصادقة الثنائية لحسابات الإدارة والمدرسين")
    return u


def _unread_notification_count(db: Session, user_id: int) -> int:
    key = f"notifications:unread:{user_id}"
    cached = cache_get_json(key)
    if isinstance(cached, int) and cached >= 0:
        return cached
    value = db.query(Notification).filter(Notification.user_id == user_id, Notification.read_at.is_(None)).count()
    cache_set_json(key, int(value), ttl=max(5, min(int(os.getenv("UNREAD_COUNT_CACHE_SECONDS", "15")), 60)))
    return int(value)


def template_context(request: Request, db: Session, **extra):
    u = current_user(request, db)
    unread = _unread_notification_count(db, u.id) if u else 0
    return {
        "request": request, "user": u, "csrf": ensure_csrf(request.session),
        "unread_notifications": unread,
        "staff_mfa_pending": bool(u and REQUIRE_STAFF_MFA and u.role in STAFF_ROLES and not u.mfa_enabled),
        "role_labels": ROLE_LABELS, "is_production": IS_PRODUCTION, **extra,
    }


def audit(db: Session, request: Request, user: User | None, action: str, metadata: dict | None = None, *, commit: bool = True):
    db.add(AuditLog(user_id=user.id if user else None, action=action, ip=client_ip(request), metadata_json=json.dumps(metadata or {}, ensure_ascii=False)))
    if commit: db.commit()
