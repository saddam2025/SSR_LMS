from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from .. import push
from ..db import get_db
from ..cache import delete as cache_delete
from ..models import Notification, PushDevice
from ..request_context import require_user, template_context as ctx
from ..security import check_csrf, ensure_csrf
from ..services.template_rendering import render_template

router = APIRouter()
@router.get("/api/mobile/push/config")
def mobile_push_config(request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    return {"csrf": ensure_csrf(request.session), "user_id": u.id, "push": push.status()}

@router.post("/api/mobile/push/register")
async def mobile_push_register(request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    payload = await request.json()
    if not check_csrf(request.session, str(payload.get("csrf", ""))): raise HTTPException(403)
    token = str(payload.get("token", "")).strip()
    if len(token) < 40 or len(token) > 2048: raise HTTPException(400, "رمز الجهاز غير صالح")
    installation_id = str(payload.get("installation_id", ""))[:255]
    device_name = str(payload.get("device_name", "Android"))[:180]
    app_version = str(payload.get("app_version", ""))[:40]
    rec = db.query(PushDevice).filter(PushDevice.push_token == token).first()
    if not rec:
        rec = PushDevice(user_id=u.id, platform="android", push_token=token, installation_id=installation_id, device_name=device_name, app_version=app_version, active=True)
        db.add(rec)
    else:
        rec.user_id=u.id; rec.platform="android"; rec.installation_id=installation_id; rec.device_name=device_name; rec.app_version=app_version; rec.active=True; rec.last_seen_at=datetime.utcnow()
    db.commit()
    return {"ok": True, "device_id": rec.id, "push_ready": push.status().get("ready", False)}

@router.post("/api/mobile/push/unregister")
async def mobile_push_unregister(request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    payload = await request.json()
    if not check_csrf(request.session, str(payload.get("csrf", ""))): raise HTTPException(403)
    token = str(payload.get("token", "")).strip()
    rec = db.query(PushDevice).filter(PushDevice.user_id==u.id, PushDevice.push_token==token).first()
    if rec: rec.active=False; db.commit()
    return {"ok": True}

@router.get("/account/push-devices", response_class=HTMLResponse)
def account_push_devices(request: Request, db: Session = Depends(get_db)):
    u=require_user(request,db)
    devices=db.query(PushDevice).filter_by(user_id=u.id).order_by(PushDevice.last_seen_at.desc()).all()
    return render_template("account_push_devices.html", ctx(request,db,devices=devices,push_status=push.status()))

@router.post("/account/push-devices/{device_id}/revoke")
def account_push_device_revoke(device_id:int, request:Request, csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    d=db.query(PushDevice).filter_by(id=device_id,user_id=u.id).first()
    if not d: raise HTTPException(404)
    d.active=False; db.commit()
    return RedirectResponse("/account/push-devices",303)

@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, db: Session = Depends(get_db)):
    u=require_user(request, db)
    items=db.query(Notification).filter_by(user_id=u.id).order_by(Notification.id.desc()).limit(100).all()
    return render_template("notifications.html", ctx(request, db, items=items))

@router.post("/notifications/read-all")
def notifications_read_all(request: Request, csrf: str=Form(...), db: Session=Depends(get_db)):
    u=require_user(request, db)
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    db.query(Notification).filter(Notification.user_id==u.id, Notification.read_at.is_(None)).update({Notification.read_at: datetime.utcnow()})
    cache_delete(f"notifications:unread:{u.id}")
    db.commit(); return RedirectResponse("/notifications",303)



