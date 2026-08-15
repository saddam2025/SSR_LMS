import ipaddress, os, socket
from datetime import datetime, timedelta
from urllib.parse import urlparse
import httpx
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..models import User, StudentProfile, Enrollment, Subscription, Homework, HomeworkSubmission, ActiveSession, LessonProgress, QuizAttempt


def _student_last_activity_map(db: Session):
    result = {}
    def keep(uid, dt):
        if uid and dt and (uid not in result or dt > result[uid]): result[uid] = dt
    for row in db.query(ActiveSession.user_id, func.max(ActiveSession.last_seen_at)).group_by(ActiveSession.user_id).all(): keep(row[0], row[1])
    for row in db.query(LessonProgress.user_id, func.max(LessonProgress.updated_at)).group_by(LessonProgress.user_id).all(): keep(row[0], row[1])
    for row in db.query(QuizAttempt.user_id, func.max(QuizAttempt.created_at)).group_by(QuizAttempt.user_id).all(): keep(row[0], row[1])
    for row in db.query(HomeworkSubmission.student_id, func.max(HomeworkSubmission.submitted_at)).group_by(HomeworkSubmission.student_id).all(): keep(row[0], row[1])
    return result


def communication_recipients(db: Session, audience_type: str, audience_value: str = ""):
    q = db.query(User).filter(User.role == "student", User.is_active == True)
    audience_value = (audience_value or "").strip()
    if audience_type == "grade":
        ids = [x.user_id for x in db.query(StudentProfile).filter(StudentProfile.grade == audience_value).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "course":
        try: course_id = int(audience_value)
        except (TypeError, ValueError): return []
        now = datetime.utcnow()
        ids = [e.user_id for e in db.query(Enrollment).filter(Enrollment.course_id == course_id, Enrollment.active == True, or_(Enrollment.expires_at == None, Enrollment.expires_at > now)).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "expiring":
        now = datetime.utcnow(); soon = now + timedelta(days=7)
        ids = [x.user_id for x in db.query(Subscription).filter(Subscription.status == "active", Subscription.ends_at != None, Subscription.ends_at > now, Subscription.ends_at <= soon).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "inactive":
        try: days=max(1,min(int(audience_value or "3"),30))
        except ValueError: days=3
        cutoff=datetime.utcnow()-timedelta(days=days); last_map=_student_last_activity_map(db)
        return [s for s in q.all() if not last_map.get(s.id) or last_map[s.id] < cutoff]
    if audience_type == "overdue_homework":
        now = datetime.utcnow(); overdue = db.query(Homework).filter(Homework.due_at != None, Homework.due_at < now).all()
        if not overdue: return []
        course_ids = {h.course_id for h in overdue}; due_ids = {h.id for h in overdue}
        enrolled = db.query(Enrollment).filter(Enrollment.course_id.in_(course_ids), Enrollment.active == True).all()
        submitted = {(x.student_id, x.homework_id) for x in db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id.in_(due_ids)).all()}
        h_by_course = {}
        for h in overdue: h_by_course.setdefault(h.course_id, []).append(h.id)
        ids = {e.user_id for e in enrolled if any((e.user_id, hid) not in submitted for hid in h_by_course.get(e.course_id, []))}
        return q.filter(User.id.in_(ids)).all() if ids else []
    return q.all()


def _safe_webhook_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("unsafe webhook URL")
    host = parsed.hostname.lower().strip(".")
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("unsafe webhook host")
    for info in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            raise ValueError("unsafe webhook address")
    return value


def send_message_webhook(channel: str, phone: str, title: str, body: str):
    env_map = {"sms": "MESSAGE_SMS_WEBHOOK_URL", "whatsapp": "WHATSAPP_MESSAGE_WEBHOOK_URL", "push": "PUSH_MESSAGE_WEBHOOK_URL"}
    raw_url = os.getenv(env_map.get(channel, ""), "").strip()
    if not raw_url: return "not_configured", "مزود القناة غير مهيأ"
    try: url = _safe_webhook_url(raw_url)
    except (ValueError, OSError): return "failed", "عنوان مزود القناة غير آمن"
    if channel in {"sms", "whatsapp"} and not phone: return "skipped", "لا يوجد رقم هاتف محفوظ"
    try:
        token = os.getenv("MESSAGE_WEBHOOK_TOKEN", "").strip(); headers = {"Content-Type":"application/json"}
        if token: headers["Authorization"] = f"Bearer {token}"
        r = httpx.post(url, json={"channel":channel,"phone":phone,"title":title,"message":body}, headers=headers, timeout=10)
        r.raise_for_status(); return "sent", "تم التسليم لمزود الرسائل"
    except Exception as exc:
        return "failed", str(exc)[:420]
