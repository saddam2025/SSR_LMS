from __future__ import annotations
from datetime import datetime
from sqlalchemy import func
from ..models import Coupon, CouponRedemption, Enrollment, Subscription, Notification


def resolve_coupon(db, code: str, user_id: int | None = None, course_id: int | None = None, *, lock: bool = False):
    code = (code or "").strip()
    if not code:
        return None
    q = db.query(Coupon).filter(func.upper(Coupon.code) == code.upper(), Coupon.active == True)
    if lock:
        q = q.with_for_update()
    cp = q.first()
    if not cp or (cp.expires_at and cp.expires_at <= datetime.utcnow()) or (cp.max_uses and cp.used_count >= cp.max_uses):
        return None
    if user_id is not None and course_id is not None:
        if db.query(CouponRedemption).filter_by(coupon_id=cp.id, user_id=user_id, course_id=course_id).first():
            return "used"
    return cp


def discounted_total(price: float, coupon) -> float:
    discount = max(0, min(100, int(getattr(coupon, "discount_percent", 0) or 0)))
    return round(float(price) * (100 - discount) / 100, 2)


def activate_paid_entitlement(db, tx, provider_id: str = ""):
    tx.status = "paid"
    tx.paid_at = datetime.utcnow()
    if provider_id:
        tx.provider_reference = provider_id
    e = db.query(Enrollment).filter_by(user_id=tx.user_id, course_id=tx.course_id).first()
    if e:
        e.active = True
        # Reset any stale expiry left over from a prior expired cycle. If we don't
        # clear this, access.py's authorized_for_course() gate sees the old,
        # already-past expires_at and locks the student out again right after they
        # paid. Subscription.ends_at (below) is what governs the new period.
        e.expires_at = None
    else:
        db.add(Enrollment(user_id=tx.user_id, course_id=tx.course_id, active=True))
    db.add(Subscription(user_id=tx.user_id, course_id=tx.course_id, amount=tx.amount, status="active", payment_ref=tx.provider_reference))
    if tx.coupon_code:
        cp = db.query(Coupon).filter(func.upper(Coupon.code) == tx.coupon_code.upper()).with_for_update().first()
        if cp and not db.query(CouponRedemption).filter_by(coupon_id=cp.id, user_id=tx.user_id, course_id=tx.course_id).first():
            cp.used_count += 1
            db.add(CouponRedemption(coupon_id=cp.id, user_id=tx.user_id, course_id=tx.course_id, payment_id=tx.id))
    return tx