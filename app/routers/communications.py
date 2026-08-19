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
from ..services.communications import communication_recipient_ids, bulk_in_app_campaign
from ..tasks import enqueue_many

router = APIRouter()


def _queue_external_deliveries(db: Session, campaign_id: int, recipient_ids: list[int], channels: list[str]) -> list[int]:
    """Persist external delivery rows and return only work that can actually run.

    A disabled provider is terminal configuration state, not asynchronous work.
    Recording it immediately avoids filling Redis/DB with jobs that a worker can
    never deliver and keeps campaign status truthful even when no worker is online.
    """
    ids: list[int] = []
    now = datetime.utcnow()
    env_map = {
        "sms": "MESSAGE_SMS_WEBHOOK_URL",
        "whatsapp": "WHATSAPP_MESSAGE_WEBHOOK_URL",
        "push": "PUSH_MESSAGE_WEBHOOK_URL",
    }
    for channel in channels:
        if channel == "in_app":
            continue
        configured = bool(os.getenv(env_map.get(channel, ""), "").strip())
        status = "queued" if configured else "not_configured"
        detail = "في انتظار عامل الإرسال" if configured else "مزود القناة غير مهيأ"
        for start in range(0, len(recipient_ids), 500):
            rows = [
                CommunicationDelivery(
                    campaign_id=campaign_id,
                    user_id=uid,
                    channel=channel,
                    status=status,
                    detail=detail,
                    created_at=now,
                )
                for uid in recipient_ids[start:start + 500]
            ]
            db.add_all(rows)
            db.flush()
            if configured:
                ids.extend(int(row.id) for row in rows)
    return ids


def _create_campaign(
    db: Session,
    *,
    created_by: int,
    title: str,
    body: str,
    audience_type: str,
    audience_value: str,
    channels: list[str],
    notification_kind: str,
) -> tuple[CommunicationCampaign, list[int], int]:
    recipient_ids = communication_recipient_ids(db, audience_type, audience_value)
    campaign = CommunicationCampaign(
        created_by=created_by,
        title=title,
        body=body,
        audience_type=audience_type,
        audience_value=audience_value,
        channels=",".join(channels),
        recipient_count=len(recipient_ids),
    )
    db.add(campaign)
    db.flush()
    if "in_app" in channels:
        bulk_in_app_campaign(
            db,
            campaign_id=campaign.id,
            recipient_ids=recipient_ids,
            title=title,
            body=body,
            kind=notification_kind,
        )
    queued_delivery_ids = _queue_external_deliveries(db, campaign.id, recipient_ids, channels)
    # Commit the durable campaign/delivery state before handing work to Redis.
    db.commit()
    queued = enqueue_many("communication_delivery", [{"delivery_id": x} for x in queued_delivery_ids])
    # A transient enqueue outage does not lose the campaign. Embedded/dedicated
    # workers recover DB rows that remain in status=queued after Redis returns.
    return campaign, recipient_ids, queued


@router.get("/admin/communications", response_class=HTMLResponse)
def admin_communications(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "support")
    campaigns = db.query(CommunicationCampaign).order_by(CommunicationCampaign.id.desc()).limit(50).all()
    courses = db.query(Course).order_by(Course.grade, Course.title).all()
    grades = [x[0] for x in db.query(StudentProfile.grade).filter(StudentProfile.grade != "").distinct().order_by(StudentProfile.grade).all()]
    statuses = {}
    for c in campaigns:
        statuses[c.id] = db.query(CommunicationDelivery.channel, CommunicationDelivery.status, func.count(CommunicationDelivery.id)).filter(CommunicationDelivery.campaign_id == c.id).group_by(CommunicationDelivery.channel, CommunicationDelivery.status).all()
    now = datetime.utcnow(); soon = now + timedelta(days=7)
    metrics = {
        "students": db.query(User).filter(User.role == "student", User.is_active == True).count(),
        "unread": db.query(Notification).filter(Notification.read_at == None).count(),
        "expiring": db.query(Subscription).filter(Subscription.status == "active", Subscription.ends_at != None, Subscription.ends_at > now, Subscription.ends_at <= soon).count(),
        "campaigns": db.query(CommunicationCampaign).count(),
    }
    providers = {
        "sms": bool(os.getenv("MESSAGE_SMS_WEBHOOK_URL", "").strip()),
        "whatsapp": bool(os.getenv("WHATSAPP_MESSAGE_WEBHOOK_URL", "").strip()),
        "push": bool(os.getenv("PUSH_MESSAGE_WEBHOOK_URL", "").strip()),
    }
    return render_template("admin_communications.html", template_context(request, db, campaigns=campaigns, courses=courses, grades=grades, statuses=statuses, metrics=metrics, providers=providers))


@router.post("/admin/communications/send")
def admin_communications_send(request: Request, title: str=Form(...), body: str=Form(...), audience_type: str=Form("all_students"), audience_value: str=Form(""), channels: list[str]=Form(["in_app"]), csrf: str=Form(...), db: Session=Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "support")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403)
    title = title.strip(); body = body.strip(); audience_value = audience_value.strip()
    if not title or not body:
        raise HTTPException(400, "العنوان ونص الرسالة مطلوبان")
    if audience_type not in {"all_students", "grade", "course", "expiring", "overdue_homework", "inactive"}:
        raise HTTPException(400, "الجمهور غير صالح")
    channels = list(dict.fromkeys(x for x in channels if x in {"in_app", "sms", "whatsapp", "push"})) or ["in_app"]
    campaign, recipient_ids, queued = _create_campaign(
        db,
        created_by=u.id,
        title=title,
        body=body,
        audience_type=audience_type,
        audience_value=audience_value,
        channels=channels,
        notification_kind="info",
    )
    audit(db, request, u, "communication_campaign_queued", {
        "campaign_id": campaign.id,
        "audience_type": audience_type,
        "recipients": len(recipient_ids),
        "channels": channels,
        "external_tasks_enqueued": queued,
    })
    return RedirectResponse("/admin/communications", 303)


@router.post("/admin/communications/quick")
def admin_communications_quick(request: Request, preset: str=Form(...), channel: str=Form("in_app"), csrf: str=Form(...), db: Session=Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "support")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403)
    presets = {
        "expiring": ("اشتراكك يقترب من الانتهاء", "اشتراكك في منصة المستشار يقترب من الانتهاء. جدّد اشتراكك لضمان استمرار الوصول إلى المحتوى.", "expiring"),
        "overdue": ("متابعة الواجبات", "لديك واجب انتهى موعده ولم يتم تسليمه بعد. ادخل إلى المنصة وأكمل المطلوب في أقرب وقت.", "overdue_homework"),
    }
    if preset not in presets:
        raise HTTPException(400, "التنبيه السريع غير صالح")
    if channel not in {"in_app", "sms", "whatsapp", "push"}:
        raise HTTPException(400, "قناة غير صالحة")
    title, body, audience = presets[preset]
    campaign, recipient_ids, queued = _create_campaign(
        db,
        created_by=u.id,
        title=title,
        body=body,
        audience_type=audience,
        audience_value="",
        channels=[channel],
        notification_kind="warning",
    )
    audit(db, request, u, "communication_quick_queued", {
        "campaign_id": campaign.id,
        "preset": preset,
        "recipients": len(recipient_ids),
        "channel": channel,
        "external_tasks_enqueued": queued,
    })
    return RedirectResponse("/admin/communications", 303)
