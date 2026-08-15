from __future__ import annotations

from datetime import datetime
from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Notification, SupportTicket, SupportTicketMessage, User
from ..permissions import SUPPORT_ROLES

ALLOWED_CATEGORIES = {"technical", "account", "payment", "content", "other"}
ALLOWED_PRIORITIES = {"low", "normal", "high"}
ALLOWED_STATUSES = {"open", "pending", "resolved", "closed"}


def create_ticket(db: Session, user: User, *, subject: str, category: str, priority: str, message: str) -> SupportTicket:
    subject = (subject or "").strip()[:180]
    message = (message or "").strip()
    if not subject or not message:
        raise HTTPException(400, "ticket_subject_and_message_required")
    if category not in ALLOWED_CATEGORIES:
        category = "other"
    if priority not in ALLOWED_PRIORITIES:
        priority = "normal"
    ticket = SupportTicket(user_id=user.id, subject=subject, category=category, priority=priority, status="open")
    db.add(ticket)
    db.flush()
    db.add(SupportTicketMessage(
        ticket_id=ticket.id,
        author_id=user.id,
        body=message[:5000],
        is_staff=user.role in SUPPORT_ROLES,
    ))
    db.commit()
    return ticket


def ticket_for_user(db: Session, ticket_id: int, user: User) -> SupportTicket:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket_not_found")
    if user.role not in SUPPORT_ROLES and ticket.user_id != user.id:
        raise HTTPException(403, "ticket_forbidden")
    return ticket


def add_reply(db: Session, ticket: SupportTicket, user: User, message: str) -> bool:
    body = (message or "").strip()
    if not body:
        raise HTTPException(400, "message_required")
    is_staff = user.role in SUPPORT_ROLES
    db.add(SupportTicketMessage(ticket_id=ticket.id, author_id=user.id, body=body[:5000], is_staff=is_staff))
    ticket.status = "pending" if is_staff else "open"
    ticket.updated_at = datetime.utcnow()
    if is_staff and ticket.user_id != user.id:
        db.add(Notification(
            user_id=ticket.user_id,
            title="رد جديد من الدعم الفني",
            body=f"تم الرد على تذكرتك: {ticket.subject}",
            kind="support",
        ))
    db.commit()
    return is_staff


def change_status(db: Session, ticket_id: int, status: str) -> SupportTicket:
    if status not in ALLOWED_STATUSES:
        raise HTTPException(400, "invalid_ticket_status")
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(404, "ticket_not_found")
    ticket.status = status
    ticket.updated_at = datetime.utcnow()
    db.commit()
    return ticket
