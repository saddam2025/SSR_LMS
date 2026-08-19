import ipaddress
import os
import socket
from datetime import datetime, timedelta
from urllib.parse import urlparse

import httpx
from sqlalchemy import exists, insert, or_
from sqlalchemy.orm import Session

from ..cache import delete_many as cache_delete_many
from ..models import (
    ActiveSession,
    CommunicationDelivery,
    Enrollment,
    Homework,
    HomeworkSubmission,
    LessonProgress,
    Notification,
    QuizAttempt,
    StudentProfile,
    Subscription,
    User,
)


def _active_student_ids_query(db: Session):
    return db.query(User.id).filter(User.role == "student", User.is_active == True)


def communication_recipient_ids(db: Session, audience_type: str, audience_value: str = "") -> list[int]:
    """Return recipient IDs with set-based SQL instead of loading every student object.

    This keeps broad communication routes predictable when the platform grows to
    thousands of students and avoids Python-side full-table activity maps.
    """
    q = _active_student_ids_query(db)
    audience_value = (audience_value or "").strip()

    if audience_type == "grade":
        q = q.join(StudentProfile, StudentProfile.user_id == User.id).filter(StudentProfile.grade == audience_value)
    elif audience_type == "course":
        try:
            course_id = int(audience_value)
        except (TypeError, ValueError):
            return []
        now = datetime.utcnow()
        q = q.join(Enrollment, Enrollment.user_id == User.id).filter(
            Enrollment.course_id == course_id,
            Enrollment.active == True,
            or_(Enrollment.expires_at == None, Enrollment.expires_at > now),
        )
    elif audience_type == "expiring":
        now = datetime.utcnow()
        soon = now + timedelta(days=7)
        q = q.join(Subscription, Subscription.user_id == User.id).filter(
            Subscription.status == "active",
            Subscription.ends_at != None,
            Subscription.ends_at > now,
            Subscription.ends_at <= soon,
        )
    elif audience_type == "inactive":
        try:
            days = max(1, min(int(audience_value or "3"), 30))
        except ValueError:
            days = 3
        cutoff = datetime.utcnow() - timedelta(days=days)
        recent_session = exists().where(ActiveSession.user_id == User.id).where(ActiveSession.last_seen_at >= cutoff)
        recent_progress = exists().where(LessonProgress.user_id == User.id).where(LessonProgress.updated_at >= cutoff)
        recent_quiz = exists().where(QuizAttempt.user_id == User.id).where(QuizAttempt.created_at >= cutoff)
        recent_homework = exists().where(HomeworkSubmission.student_id == User.id).where(HomeworkSubmission.submitted_at >= cutoff)
        q = q.filter(~recent_session, ~recent_progress, ~recent_quiz, ~recent_homework)
    elif audience_type == "overdue_homework":
        now = datetime.utcnow()
        # A student is included when one of their active course enrollments has an
        # overdue homework for which no submission exists from that student.
        missing_submission = ~exists().where(
            HomeworkSubmission.homework_id == Homework.id,
            HomeworkSubmission.student_id == User.id,
        )
        missing_overdue = exists().where(
            Homework.course_id == Enrollment.course_id,
            Homework.due_at != None,
            Homework.due_at < now,
            missing_submission,
        )
        q = q.join(Enrollment, Enrollment.user_id == User.id).filter(Enrollment.active == True, missing_overdue)
    elif audience_type != "all_students":
        return []

    # DISTINCT protects against students with multiple subscriptions/enrollments.
    return [int(row[0]) for row in q.distinct().order_by(User.id).all()]


def communication_recipients(db: Session, audience_type: str, audience_value: str = ""):
    """Compatibility wrapper for older call sites."""
    ids = communication_recipient_ids(db, audience_type, audience_value)
    if not ids:
        return []
    return db.query(User).filter(User.id.in_(ids)).order_by(User.id).all()


def bulk_in_app_campaign(
    db: Session,
    *,
    campaign_id: int,
    recipient_ids: list[int],
    title: str,
    body: str,
    kind: str = "info",
    detail: str = "تم إنشاء إشعار داخل المنصة",
) -> int:
    """Insert in-app notifications/delivery audit rows in bounded SQL batches."""
    if not recipient_ids:
        return 0
    now = datetime.utcnow()
    batch_size = 500
    for start in range(0, len(recipient_ids), batch_size):
        batch = recipient_ids[start:start + batch_size]
        db.execute(insert(Notification), [
            {"user_id": uid, "title": title, "body": body, "kind": kind, "created_at": now}
            for uid in batch
        ])
        db.execute(insert(CommunicationDelivery), [
            {
                "campaign_id": campaign_id,
                "user_id": uid,
                "channel": "in_app",
                "status": "sent",
                "detail": detail,
                "sent_at": now,
                "created_at": now,
            }
            for uid in batch
        ])
    # Unread counters are short-lived, but invalidating them prevents a user who
    # opens the page immediately after a campaign from seeing a stale count.
    cache_delete_many([f"notifications:unread:{uid}" for uid in recipient_ids])
    return len(recipient_ids)


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


def send_message_webhook(channel: str, phone: str, title: str, body: str, *, idempotency_key: str = ""):
    env_map = {"sms": "MESSAGE_SMS_WEBHOOK_URL", "whatsapp": "WHATSAPP_MESSAGE_WEBHOOK_URL", "push": "PUSH_MESSAGE_WEBHOOK_URL"}
    raw_url = os.getenv(env_map.get(channel, ""), "").strip()
    if not raw_url:
        return "not_configured", "مزود القناة غير مهيأ"
    try:
        url = _safe_webhook_url(raw_url)
    except (ValueError, OSError):
        return "failed", "عنوان مزود القناة غير آمن"
    if channel in {"sms", "whatsapp"} and not phone:
        return "skipped", "لا يوجد رقم هاتف محفوظ"
    try:
        token = os.getenv("MESSAGE_WEBHOOK_TOKEN", "").strip()
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key[:180]
        r = httpx.post(
            url,
            json={"channel": channel, "phone": phone, "title": title, "message": body, "idempotency_key": idempotency_key},
            headers=headers,
            timeout=httpx.Timeout(10.0, connect=3.0),
        )
        r.raise_for_status()
        return "sent", "تم التسليم لمزود الرسائل"
    except Exception as exc:
        return "failed", str(exc)[:420]
