from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import SupportTicket, SupportTicketMessage, User
from ..permissions import SUPPORT_ROLES
from ..security import check_csrf
from ..services.support import add_reply, change_status, create_ticket, ticket_for_user
from ..request_context import require_user, require_role, template_context, audit

router = APIRouter(tags=["support"])


def _require_user(request: Request, db: Session):
    return require_user(request, db)


def _require_role(request: Request, db: Session, *roles):
    return require_role(request, db, *roles)


def _ctx(request: Request, db: Session, **extra):
    return template_context(request, db, **extra)


def _render(request: Request, name: str, context: dict):
    return request.app.state.render_template(name, context)


def _audit(request: Request, db: Session, user: User, action: str, metadata: dict):
    return audit(db, request, user, action, metadata)


@router.get("/support", response_class=HTMLResponse)
def support_center(request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if user.role in SUPPORT_ROLES:
        tickets = db.query(SupportTicket).order_by(SupportTicket.updated_at.desc()).limit(200).all()
        owners = {x.id: x for x in db.query(User).filter(User.id.in_([t.user_id for t in tickets] or [-1])).all()}
        return _render(request, "support_admin.html", _ctx(request, db, tickets=tickets, owners=owners))
    tickets = db.query(SupportTicket).filter(SupportTicket.user_id == user.id).order_by(SupportTicket.updated_at.desc()).all()
    return _render(request, "support.html", _ctx(request, db, tickets=tickets))


@router.post("/support/tickets")
def support_create_ticket(request: Request, subject: str = Form(...), category: str = Form("technical"),
                          priority: str = Form("normal"), message: str = Form(...), csrf: str = Form(...),
                          db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not check_csrf(request.session, csrf):
        raise HTTPException(403, "csrf_failed")
    ticket = create_ticket(db, user, subject=subject, category=category, priority=priority, message=message)
    _audit(request, db, user, "support_ticket_created", {"ticket_id": ticket.id})
    return RedirectResponse(f"/support/tickets/{ticket.id}", 303)


@router.get("/support/tickets/{ticket_id}", response_class=HTMLResponse)
def support_ticket_view(ticket_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    ticket = ticket_for_user(db, ticket_id, user)
    messages = db.query(SupportTicketMessage).filter_by(ticket_id=ticket.id).order_by(SupportTicketMessage.created_at).all()
    authors = {x.id: x for x in db.query(User).filter(User.id.in_([m.author_id for m in messages] or [-1])).all()}
    return _render(request, "support_ticket.html", _ctx(request, db, ticket=ticket, messages=messages, authors=authors))


@router.post("/support/tickets/{ticket_id}/reply")
def support_ticket_reply(ticket_id: int, request: Request, message: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    user = _require_user(request, db)
    if not check_csrf(request.session, csrf):
        raise HTTPException(403, "csrf_failed")
    ticket = ticket_for_user(db, ticket_id, user)
    is_staff = add_reply(db, ticket, user, message)
    _audit(request, db, user, "support_ticket_replied", {"ticket_id": ticket.id, "staff": is_staff})
    return RedirectResponse(f"/support/tickets/{ticket.id}", 303)


@router.post("/support/tickets/{ticket_id}/status")
def support_ticket_status(ticket_id: int, request: Request, status: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    user = _require_role(request, db, "super_admin", "admin", "support")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403, "csrf_failed")
    ticket = change_status(db, ticket_id, status)
    _audit(request, db, user, "support_ticket_status_changed", {"ticket_id": ticket.id, "status": status})
    return RedirectResponse(f"/support/tickets/{ticket.id}", 303)
