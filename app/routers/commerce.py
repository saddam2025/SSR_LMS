from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from ..db import engine, get_db
from ..models import (
    ActivationCode, Coupon, CouponRedemption, Course, Enrollment, Notification,
    PaymentTransaction, Subscription, User,
)
from ..payment import create_intention, configured as paymob_configured, merchant_reference, verify_transaction_hmac
from ..request_context import audit, require_role, require_user, template_context as ctx
from ..security import check_csrf
from ..services.commerce import activate_paid_entitlement, discounted_total, resolve_coupon

router = APIRouter(tags=["commerce"])
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")


def _render(name: str, context: dict, status_code: int = 200):
    request = context.get("request")
    return Jinja2Templates.TemplateResponse(templates, request=request, name=name, context=context, status_code=status_code)


def _normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("20") and len(digits) == 12:
        digits = "0" + digits[2:]
    if len(digits) == 10 and digits.startswith("1"):
        digits = "0" + digits
    return digits[:15]


def _pg_xact_lock(db: Session, namespace: int, entity_id: int):
    if engine.dialect.name == "postgresql":
        safe_entity = int(entity_id) & 0x7FFFFFFF
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :entity)"), {"ns": int(namespace), "entity": safe_entity})


@router.get("/checkout/{course_id}", response_class=HTMLResponse)
def checkout_page(course_id: int, request: Request, coupon: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    c = db.get(Course, course_id)
    if not c or not c.published:
        raise HTTPException(404)
    existing = db.query(Enrollment).filter_by(user_id=u.id, course_id=c.id, active=True).first()
    if existing:
        return RedirectResponse(f"/course/{c.id}", 302)
    coupon_obj = None
    error = None
    if coupon:
        coupon_obj = resolve_coupon(db, coupon)
        if not coupon_obj:
            error = "كود الخصم غير صالح أو انتهت صلاحيته."
    total = discounted_total(c.price, coupon_obj)
    return _render("checkout.html", ctx(request, db, course=c, coupon=coupon_obj, total=total, error=error, paymob_ready=paymob_configured()))


@router.post("/checkout/{course_id}")
def checkout_start(course_id: int, request: Request, phone: str = Form(...), coupon_code: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c or not c.published:
        raise HTTPException(404)
    phone = _normalize_phone(phone)
    if len(phone) != 11 or not phone.startswith("01"):
        raise HTTPException(400, "أدخل رقم موبايل مصري صحيح مكونًا من 11 رقمًا")
    cp = None
    if coupon_code.strip():
        cp = resolve_coupon(db, coupon_code, u.id, c.id, lock=True)
        if cp == "used":
            raise HTTPException(409, "تم استخدام هذا الكوبون من قبل")
        if not cp:
            return RedirectResponse(f"/checkout/{course_id}?coupon={coupon_code}", 303)
    total = discounted_total(c.price, cp)
    if total <= 0:
        e = db.query(Enrollment).filter_by(user_id=u.id, course_id=c.id).first()
        if e:
            e.active = True
        else:
            db.add(Enrollment(user_id=u.id, course_id=c.id, active=True))
        tx = PaymentTransaction(user_id=u.id, course_id=c.id, provider="coupon", merchant_reference=merchant_reference(), amount=0, status="paid", coupon_code=cp.code if cp else "", paid_at=datetime.utcnow())
        db.add(tx); db.flush()
        if cp:
            cp.used_count += 1
            db.add(CouponRedemption(coupon_id=cp.id, user_id=u.id, course_id=c.id, payment_id=tx.id))
        db.add(Notification(user_id=u.id, title="تم تفعيل الكورس", body=f"تم تفعيل اشتراكك في {c.title} بنجاح.", kind="success"))
        db.commit(); audit(db, request, u, "course_activated_free", {"course_id": c.id})
        return RedirectResponse(f"/course/{c.id}", 303)
    if not paymob_configured():
        raise HTTPException(503, "بوابة الدفع لم تُفعّل بعد. أضف بيانات Paymob في متغيرات البيئة.")
    ref = merchant_reference()
    tx = PaymentTransaction(user_id=u.id, course_id=c.id, merchant_reference=ref, amount=total, currency="EGP", coupon_code=cp.code if cp else "", status="pending")
    db.add(tx); db.commit()
    try:
        data, url = create_intention(amount_egp=total, course_title=c.title, reference=ref, name=u.name, email=u.email, phone=phone, base_url=(PUBLIC_BASE_URL or str(request.base_url).rstrip('/')))
        tx.provider_reference = str(data.get("id", "")); db.commit(); audit(db, request, u, "payment_intention_created", {"payment_id": tx.id, "course_id": c.id})
        return RedirectResponse(url, 303)
    except Exception as ex:
        tx.status = "failed_to_initialize"; db.commit(); audit(db, request, u, "payment_intention_failed", {"payment_id": tx.id, "error": type(ex).__name__})
        raise HTTPException(502, "تعذر بدء عملية الدفع حاليًا.")


@router.post("/api/paymob/webhook")
async def paymob_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json(); obj = payload.get("obj") or payload
    received = request.query_params.get("hmac", "")
    if not verify_transaction_hmac(obj, received):
        raise HTTPException(403, "Invalid HMAC")
    ref = str((obj.get("order") or {}).get("merchant_order_id") or obj.get("merchant_order_id") or "")
    if not ref:
        ref = str(obj.get("special_reference") or "")
    tx = db.query(PaymentTransaction).filter_by(merchant_reference=ref).with_for_update().first()
    if not tx:
        return {"ok": True}
    expected_integration = str(os.getenv("PAYMOB_INTEGRATION_ID", ""))
    if expected_integration and str(obj.get("integration_id") or "") != expected_integration:
        raise HTTPException(403, "Unexpected integration")
    provider_id = str(obj.get("id") or "")
    if provider_id:
        other = db.query(PaymentTransaction).filter(PaymentTransaction.provider_reference == provider_id, PaymentTransaction.id != tx.id, PaymentTransaction.status == "paid").first()
        if other:
            raise HTTPException(409, "Duplicate provider transaction")
    expected_cents = int(round(tx.amount * 100))
    amount_ok = int(obj.get("amount_cents") or -1) == expected_cents
    currency_ok = str(obj.get("currency") or "").upper() == tx.currency.upper()
    success = bool(obj.get("success")) and not bool(obj.get("pending")) and not bool(obj.get("error_occured")) and amount_ok and currency_ok
    tx.provider_reference = provider_id or tx.provider_reference
    if tx.status == "paid":
        db.commit(); return {"ok": True}
    if success and tx.status != "paid":
        _pg_xact_lock(db, 5503, (int(tx.user_id) * 1000003 + int(tx.course_id)))
        activate_paid_entitlement(db, tx, provider_id)
        c = db.get(Course, tx.course_id)
        db.add(Notification(user_id=tx.user_id, title="تم تأكيد الدفع", body=f"تم تفعيل {c.title if c else 'الكورس'} بنجاح.", kind="success"))
    elif not success:
        tx.status = "verification_failed" if (not amount_ok or not currency_ok) else "declined"
    db.commit(); return {"ok": True}


@router.get("/payment/complete", response_class=HTMLResponse)
def payment_complete(request: Request, db: Session = Depends(get_db)):
    require_user(request, db)
    return _render("payment_complete.html", ctx(request, db))


@router.get("/admin/commerce", response_class=HTMLResponse)
def admin_commerce(request: Request, student_q: str = "", db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "accounting")
    now = datetime.utcnow(); month_start = now - timedelta(days=30); soon = now + timedelta(days=7)
    coupons = db.query(Coupon).order_by(Coupon.id.desc()).all()
    payments = db.query(PaymentTransaction).order_by(PaymentTransaction.id.desc()).limit(100).all()
    subscriptions = db.query(Subscription).order_by(Subscription.starts_at.desc()).limit(150).all()
    codes = db.query(ActivationCode).order_by(ActivationCode.id.desc()).limit(100).all()
    courses = db.query(Course).order_by(Course.title).all()
    student_q = " ".join((student_q or "").strip().split())[:120]
    student_query = db.query(User).filter(User.role == "student", User.is_active == True)
    if student_q:
        like = f"%{student_q}%"
        student_query = student_query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    students = student_query.order_by(User.id.desc()).limit(50).all()
    user_ids = {x.user_id for x in payments} | {x.user_id for x in subscriptions}
    users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    course_ids = {x.course_id for x in payments} | {x.course_id for x in subscriptions} | {x.course_id for x in codes}
    course_map = {c.id: c for c in db.query(Course).filter(Course.id.in_(course_ids)).all()} if course_ids else {}
    paid = db.query(PaymentTransaction).filter(PaymentTransaction.status == "paid")
    revenue_total = float(paid.with_entities(func.coalesce(func.sum(PaymentTransaction.amount), 0)).scalar() or 0)
    revenue_30 = float(paid.filter(PaymentTransaction.paid_at >= month_start).with_entities(func.coalesce(func.sum(PaymentTransaction.amount), 0)).scalar() or 0)
    paid_count = paid.count(); pending_count = db.query(PaymentTransaction).filter(PaymentTransaction.status == "pending").count()
    failed_count = db.query(PaymentTransaction).filter(PaymentTransaction.status.in_(["declined", "verification_failed", "failed_to_initialize"])).count()
    active_subscriptions = db.query(Subscription).filter(Subscription.status == "active", or_(Subscription.ends_at == None, Subscription.ends_at > now)).count()
    expiring_subscriptions = db.query(Subscription).filter(Subscription.status == "active", Subscription.ends_at != None, Subscription.ends_at > now, Subscription.ends_at <= soon).count()
    expired_subscriptions = db.query(Subscription).filter(or_(Subscription.status == "expired", Subscription.ends_at <= now)).count()
    metrics = {"revenue_total": revenue_total, "revenue_30": revenue_30, "paid_count": paid_count, "pending_count": pending_count, "failed_count": failed_count, "active_subscriptions": active_subscriptions, "expiring_subscriptions": expiring_subscriptions, "expired_subscriptions": expired_subscriptions}
    return _render("admin_commerce.html", ctx(request, db, coupons=coupons, payments=payments, subscriptions=subscriptions, paymob_ready=paymob_configured(), activation_codes=codes, courses=courses, students=students, student_q=student_q, users=users, course_map=course_map, metrics=metrics, now=now, soon=soon))


@router.post("/admin/coupons")
def admin_coupon_create(request: Request, code: str = Form(...), discount_percent: int = Form(...), max_uses: int = Form(0), expires_at: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "accounting")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403)
    code = code.strip().upper()
    if not code or db.query(Coupon).filter(func.upper(Coupon.code) == code).first():
        raise HTTPException(409, "الكود موجود بالفعل")
    expiry = None
    if expires_at.strip():
        try: expiry = datetime.fromisoformat(expires_at.strip())
        except ValueError: raise HTTPException(400, "تاريخ انتهاء الكوبون غير صالح")
    db.add(Coupon(code=code, discount_percent=max(0, min(100, discount_percent)), max_uses=max(0, max_uses), active=True, expires_at=expiry)); db.commit(); audit(db, request, u, "coupon_created", {"code": code, "expires_at": expiry.isoformat() if expiry else None})
    return RedirectResponse("/admin/commerce", 303)


@router.post("/admin/coupons/{coupon_id}/toggle")
def admin_coupon_toggle(coupon_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "accounting")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    cp = db.get(Coupon, coupon_id)
    if not cp: raise HTTPException(404)
    cp.active = not cp.active; db.commit(); audit(db, request, u, "coupon_toggled", {"coupon_id": cp.id, "active": cp.active})
    return RedirectResponse("/admin/commerce", 303)


@router.post("/admin/subscriptions/grant")
def admin_subscription_grant(request: Request, user_id: int = Form(...), course_id: int = Form(...), duration_days: int = Form(0), amount: float = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "accounting")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    student = db.get(User, user_id); course = db.get(Course, course_id)
    if not student or student.role != "student" or not course: raise HTTPException(404)
    now = datetime.utcnow(); ends = now + timedelta(days=max(1, min(duration_days, 3650))) if duration_days > 0 else None
    e = db.query(Enrollment).filter_by(user_id=user_id, course_id=course_id).first()
    if e: e.active = True
    else: db.add(Enrollment(user_id=user_id, course_id=course_id, active=True))
    sub = Subscription(user_id=user_id, course_id=course_id, amount=max(0, amount), status="active", payment_ref="manual", starts_at=now, ends_at=ends); db.add(sub)
    db.add(Notification(user_id=user_id, title="تم تفعيل اشتراكك", body=f"تم تفعيل {course.title} بواسطة إدارة المنصة.", kind="success")); db.commit(); audit(db, request, u, "subscription_granted", {"subscription_id": sub.id, "user_id": user_id, "course_id": course_id, "duration_days": duration_days})
    return RedirectResponse("/admin/commerce", 303)


@router.post("/admin/subscriptions/{subscription_id}/extend")
def admin_subscription_extend(subscription_id: int, request: Request, days: int = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "accounting")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    sub = db.get(Subscription, subscription_id)
    if not sub: raise HTTPException(404)
    days = max(1, min(days, 3650)); base = sub.ends_at if sub.ends_at and sub.ends_at > datetime.utcnow() else datetime.utcnow(); sub.ends_at = base + timedelta(days=days); sub.status = "active"
    e = db.query(Enrollment).filter_by(user_id=sub.user_id, course_id=sub.course_id).first()
    if e: e.active = True
    db.commit(); audit(db, request, u, "subscription_extended", {"subscription_id": sub.id, "days": days})
    return RedirectResponse("/admin/commerce", 303)


@router.post("/admin/subscriptions/{subscription_id}/status")
def admin_subscription_status(subscription_id: int, request: Request, status: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "accounting")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    sub = db.get(Subscription, subscription_id)
    if not sub: raise HTTPException(404)
    if status not in {"active", "cancelled", "expired"}: raise HTTPException(400, "حالة الاشتراك غير صالحة")
    sub.status = status
    e = db.query(Enrollment).filter_by(user_id=sub.user_id, course_id=sub.course_id).first()
    if e: e.active = (status == "active")
    db.commit(); audit(db, request, u, "subscription_status_changed", {"subscription_id": sub.id, "status": status})
    return RedirectResponse("/admin/commerce", 303)
