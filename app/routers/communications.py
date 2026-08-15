import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Course, StudentProfile, Subscription, Notification, CommunicationCampaign, CommunicationDelivery
from ..request_context import require_role, audit, template_context
from ..security import check_csrf
from ..services.template_rendering import render_template
from ..services.communications import communication_recipients, send_message_webhook

router = APIRouter()

@router.get("/admin/communications", response_class=HTMLResponse)
def admin_communications(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "support")
    campaigns = db.query(CommunicationCampaign).order_by(CommunicationCampaign.id.desc()).limit(50).all()
    courses = db.query(Course).order_by(Course.grade, Course.title).all()
    grades = [x[0] for x in db.query(StudentProfile.grade).filter(StudentProfile.grade != "").distinct().order_by(StudentProfile.grade).all()]
    statuses = {}
    for c in campaigns:
        statuses[c.id] = db.query(CommunicationDelivery.channel, CommunicationDelivery.status, func.count(CommunicationDelivery.id)).filter(CommunicationDelivery.campaign_id == c.id).group_by(CommunicationDelivery.channel, CommunicationDelivery.status).all()
    now=datetime.utcnow(); soon=now+timedelta(days=7)
    metrics={"students":db.query(User).filter(User.role=="student",User.is_active==True).count(),"unread":db.query(Notification).filter(Notification.read_at==None).count(),"expiring":db.query(Subscription).filter(Subscription.status=="active",Subscription.ends_at!=None,Subscription.ends_at>now,Subscription.ends_at<=soon).count(),"campaigns":db.query(CommunicationCampaign).count()}
    providers={"sms":bool(os.getenv("MESSAGE_SMS_WEBHOOK_URL","").strip()),"whatsapp":bool(os.getenv("WHATSAPP_MESSAGE_WEBHOOK_URL","").strip()),"push":bool(os.getenv("PUSH_MESSAGE_WEBHOOK_URL","").strip())}
    return render_template("admin_communications.html", template_context(request, db, campaigns=campaigns, courses=courses, grades=grades, statuses=statuses, metrics=metrics, providers=providers))

@router.post("/admin/communications/send")
def admin_communications_send(request: Request, title: str=Form(...), body: str=Form(...), audience_type: str=Form("all_students"), audience_value: str=Form(""), channels: list[str]=Form(["in_app"]), csrf: str=Form(...), db: Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","support")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    title=title.strip(); body=body.strip()
    if not title or not body: raise HTTPException(400,"العنوان ونص الرسالة مطلوبان")
    if audience_type not in {"all_students","grade","course","expiring","overdue_homework","inactive"}: raise HTTPException(400,"الجمهور غير صالح")
    channels=[x for x in channels if x in {"in_app","sms","whatsapp","push"}] or ["in_app"]
    recipients=communication_recipients(db,audience_type,audience_value)
    campaign=CommunicationCampaign(created_by=u.id,title=title,body=body,audience_type=audience_type,audience_value=audience_value,channels=",".join(channels),recipient_count=len(recipients)); db.add(campaign); db.flush()
    profiles={p.user_id:p for p in db.query(StudentProfile).filter(StudentProfile.user_id.in_([r.id for r in recipients])).all()} if recipients else {}; now=datetime.utcnow()
    for recipient in recipients:
        phone=(profiles.get(recipient.id).phone if profiles.get(recipient.id) else "")
        for channel in channels:
            if channel == "in_app": db.add(Notification(user_id=recipient.id,title=title,body=body,kind="info")); status,detail="sent","تم إنشاء إشعار داخل المنصة"
            else: status,detail=send_message_webhook(channel,phone,title,body)
            db.add(CommunicationDelivery(campaign_id=campaign.id,user_id=recipient.id,channel=channel,status=status,detail=detail,sent_at=now if status=="sent" else None))
    db.commit(); audit(db,request,u,"communication_campaign_sent",{"campaign_id":campaign.id,"audience_type":audience_type,"recipients":len(recipients),"channels":channels})
    return RedirectResponse("/admin/communications",303)

@router.post("/admin/communications/quick")
def admin_communications_quick(request: Request, preset: str=Form(...), channel: str=Form("in_app"), csrf: str=Form(...), db: Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","support")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    presets={"expiring":("اشتراكك يقترب من الانتهاء","اشتراكك في منصة المستشار يقترب من الانتهاء. جدّد اشتراكك لضمان استمرار الوصول إلى المحتوى.","expiring"),"overdue":("متابعة الواجبات","لديك واجب انتهى موعده ولم يتم تسليمه بعد. ادخل إلى المنصة وأكمل المطلوب في أقرب وقت.","overdue_homework")}
    if preset not in presets: raise HTTPException(400,"التنبيه السريع غير صالح")
    if channel not in {"in_app","sms","whatsapp","push"}: raise HTTPException(400,"قناة غير صالحة")
    title,body,audience=presets[preset]; recipients=communication_recipients(db,audience,"")
    campaign=CommunicationCampaign(created_by=u.id,title=title,body=body,audience_type=audience,audience_value="",channels=channel,recipient_count=len(recipients)); db.add(campaign); db.flush()
    profiles={p.user_id:p for p in db.query(StudentProfile).filter(StudentProfile.user_id.in_([x.id for x in recipients])).all()} if recipients else {}; now=datetime.utcnow()
    for r in recipients:
        if channel=="in_app": db.add(Notification(user_id=r.id,title=title,body=body,kind="warning")); status,detail="sent","تم إنشاء إشعار داخل المنصة"
        else: status,detail=send_message_webhook(channel,(profiles.get(r.id).phone if profiles.get(r.id) else ""),title,body)
        db.add(CommunicationDelivery(campaign_id=campaign.id,user_id=r.id,channel=channel,status=status,detail=detail,sent_at=now if status=="sent" else None))
    db.commit(); audit(db,request,u,"communication_quick_sent",{"campaign_id":campaign.id,"preset":preset,"recipients":len(recipients),"channel":channel})
    return RedirectResponse("/admin/communications",303)
