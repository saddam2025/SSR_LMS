from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ActiveSession, Device, User
from ..request_context import audit, require_role, template_context as ctx
from ..security import check_csrf
from ..services.template_rendering import render_template

router = APIRouter()

@router.get("/admin/security", response_class=HTMLResponse)
def admin_security(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    devices = db.query(Device).order_by(Device.last_seen_at.desc()).limit(100).all()
    sessions = db.query(ActiveSession).filter(ActiveSession.revoked_at.is_(None)).order_by(ActiveSession.last_seen_at.desc()).limit(100).all()
    users = {u.id: u for u in db.query(User).all()}
    return render_template("admin_security.html", ctx(request, db, devices=devices, sessions=sessions, users=users))

@router.post("/admin/security/device/{device_id}/toggle")
def toggle_device(device_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    device = db.get(Device, device_id)
    if not device: raise HTTPException(404)
    device.blocked = not device.blocked
    if device.blocked:
        now = datetime.utcnow()
        db.query(ActiveSession).filter(ActiveSession.device_id == device.id, ActiveSession.revoked_at.is_(None)).update({ActiveSession.revoked_at: now})
    db.commit(); audit(db, request, u, "device_block_toggled", {"device_id": device.id, "blocked": device.blocked})
    return RedirectResponse("/admin/security", 303)

@router.post("/admin/security/session/{session_id}/revoke")
def revoke_session(session_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    session = db.get(ActiveSession, session_id)
    if not session: raise HTTPException(404)
    session.revoked_at = datetime.utcnow(); db.commit()
    audit(db, request, u, "session_revoked", {"session_id": session.id, "target_user": session.user_id})
    return RedirectResponse("/admin/security", 303)
