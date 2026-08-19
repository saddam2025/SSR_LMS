"""Background task handlers for Mostashar.

The default production mode embeds one lightweight Redis-stream consumer per
Uvicorn worker. A dedicated Railway worker service can instead run this module
with TASK_WORKER_MODE=dedicated.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime

from .db import SessionLocal
from .models import CommunicationCampaign, CommunicationDelivery, StudentProfile, User
from .services.communications import send_message_webhook
from .tasks import enqueue_many, run_worker

_thread: threading.Thread | None = None
_stop_event: threading.Event | None = None
_lock = threading.Lock()


def communication_delivery(payload: dict) -> None:
    try:
        delivery_id = int(payload.get("delivery_id", 0))
    except (TypeError, ValueError):
        return
    if delivery_id <= 0:
        return
    db = SessionLocal()
    try:
        delivery = db.get(CommunicationDelivery, delivery_id)
        if not delivery or delivery.status not in {"queued", "retry"}:
            return
        campaign = db.get(CommunicationCampaign, delivery.campaign_id)
        user = db.get(User, delivery.user_id)
        if not campaign or not user or not user.is_active:
            delivery.status = "skipped"
            delivery.detail = "المستلم غير متاح"
            db.commit()
            return
        profile = db.query(StudentProfile).filter(StudentProfile.user_id == user.id).first()
        phone = profile.phone if profile else ""
        status, detail = send_message_webhook(
            delivery.channel,
            phone,
            campaign.title,
            campaign.body,
            idempotency_key=f"mostashar-communication-{delivery.id}",
        )
        delivery.status = status
        delivery.detail = detail
        delivery.sent_at = datetime.utcnow() if status == "sent" else None
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _recover_queued_deliveries(limit: int = 500) -> int:
    """Requeue durable DB rows after a short Redis outage or process restart."""
    db = SessionLocal()
    try:
        ids = [row[0] for row in db.query(CommunicationDelivery.id).filter(CommunicationDelivery.status == "queued").order_by(CommunicationDelivery.id).limit(limit).all()]
    finally:
        db.close()
    if not ids:
        return 0
    return enqueue_many("communication_delivery", [{"delivery_id": x} for x in ids])


def handlers():
    return {"communication_delivery": communication_delivery}


def _run_embedded() -> None:
    # Any queued DB deliveries that missed enqueue during a transient Redis outage
    # are harmlessly re-enqueued; the handler is idempotent by delivery status.
    try:
        _recover_queued_deliveries()
    except Exception:
        pass
    run_worker(handlers(), stop_event=_stop_event)


def start_background_worker() -> bool:
    global _thread, _stop_event
    if os.getenv("TASK_WORKER_MODE", "embedded").strip().lower() not in {"embedded", "web"}:
        return False
    if not os.getenv("REDIS_URL", "").strip():
        return False
    with _lock:
        if _thread and _thread.is_alive():
            return True
        _stop_event = threading.Event()
        _thread = threading.Thread(target=_run_embedded, name="mostashar-task-worker", daemon=True)
        _thread.start()
        return True


def stop_background_worker() -> None:
    global _stop_event
    if _stop_event is not None:
        _stop_event.set()


if __name__ == "__main__":
    # Dedicated-worker mode for operators who later split web and background work
    # into separate Railway services.
    run_worker(handlers())
