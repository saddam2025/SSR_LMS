from datetime import datetime
from sqlalchemy.orm import Session
from ..models import ActivationCode, ActivationCodeInventory, ActivationRedemption, Enrollment, Notification


def batch_rows(db: Session, batch_id: int):
    inv = db.query(ActivationCodeInventory).filter_by(batch_id=batch_id).order_by(ActivationCodeInventory.serial_no).all()
    code_ids = [x.activation_code_id for x in inv]
    cmap = {x.id: x for x in db.query(ActivationCode).filter(ActivationCode.id.in_(code_ids)).all()} if code_ids else {}
    return [(x, cmap.get(x.activation_code_id)) for x in inv]


def redeem_code(db: Session, *, user_id: int, raw_code: str):
    value = (raw_code or "").strip().upper()
    now = datetime.utcnow()
    ac = db.query(ActivationCode).filter_by(code=value, active=True).with_for_update().first()
    if not ac or (ac.expires_at and ac.expires_at <= now) or (ac.max_uses and ac.used_count >= ac.max_uses):
        return None, "invalid"
    if db.query(ActivationRedemption).filter_by(activation_code_id=ac.id, user_id=user_id).first():
        return None, "already_used"
    enrollment = db.query(Enrollment).filter_by(user_id=user_id, course_id=ac.course_id).first()
    if enrollment:
        enrollment.active = True
    else:
        db.add(Enrollment(user_id=user_id, course_id=ac.course_id, active=True))
    ac.used_count += 1
    db.add(ActivationRedemption(activation_code_id=ac.id, user_id=user_id, course_id=ac.course_id))
    db.add(Notification(user_id=user_id, title="تم تفعيل الكورس", body=f"تم قبول كود الاشتراك {value}", kind="success"))
    return ac, "ok"
