import json
import os
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import event
from sqlalchemy.orm import Session
from .db import SessionLocal
from .models import Notification, PushDevice

_executor = ThreadPoolExecutor(max_workers=max(1, int(os.getenv("FCM_WORKERS", "2"))))
_firebase_app = None
_init_attempted = False

def configured() -> bool:
    return os.getenv("FCM_ENABLED", "false").lower() in {"1","true","yes","on"}

def _init_firebase():
    global _firebase_app, _init_attempted
    if _init_attempted:
        return _firebase_app
    _init_attempted = True
    if not configured():
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials
        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            return _firebase_app
        raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
        project_id = os.getenv("FIREBASE_PROJECT_ID", "").strip() or None
        if raw:
            cred = credentials.Certificate(json.loads(raw))
            _firebase_app = firebase_admin.initialize_app(cred, {"projectId": project_id} if project_id else None)
        else:
            # Uses GOOGLE_APPLICATION_CREDENTIALS / workload identity when configured by the host.
            _firebase_app = firebase_admin.initialize_app(options={"projectId": project_id} if project_id else None)
        return _firebase_app
    except Exception as exc:
        print(f"[push] Firebase init unavailable: {exc}")
        return None

def status() -> dict:
    app = _init_firebase()
    return {"enabled": configured(), "ready": app is not None, "project_id": os.getenv("FIREBASE_PROJECT_ID", "")}

def send_to_user(user_id: int, title: str, body: str, path: str = "/notifications", kind: str = "info") -> dict:
    if _init_firebase() is None:
        return {"sent": 0, "failed": 0, "skipped": True}
    from firebase_admin import messaging
    db = SessionLocal()
    try:
        devices = db.query(PushDevice).filter(PushDevice.user_id == user_id, PushDevice.active == True).all()
        sent = failed = 0
        for dev in devices:
            try:
                kwargs = dict(
                    notification=messaging.Notification(title=title[:180], body=(body or "")[:500]),
                    data={"path": path or "/notifications", "kind": kind or "info"},
                    android=messaging.AndroidConfig(priority="high", notification=messaging.AndroidNotification(channel_id="mostashar_platform")),
                )
                # Registration tokens remain supported by Android FCM. Keep installation_id for forward migration.
                msg = messaging.Message(token=dev.push_token, **kwargs)
                messaging.send(msg)
                sent += 1
            except Exception as exc:
                failed += 1
                name = exc.__class__.__name__
                if name in {"UnregisteredError", "SenderIdMismatchError", "InvalidArgumentError"}:
                    dev.active = False
                print(f"[push] send failed device={dev.id}: {name}: {exc}")
        db.commit()
        return {"sent": sent, "failed": failed, "skipped": False}
    finally:
        db.close()

def _notification_path(kind: str) -> str:
    return "/notifications"

@event.listens_for(Session, "after_flush")
def _capture_notifications(session, flush_context):
    batch = session.info.setdefault("_pending_push_notifications", [])
    for obj in session.new:
        if isinstance(obj, Notification):
            batch.append((obj.user_id, obj.title, obj.body, _notification_path(obj.kind), obj.kind))

@event.listens_for(Session, "after_commit")
def _dispatch_notifications(session):
    batch = session.info.pop("_pending_push_notifications", [])
    if not configured():
        return
    for item in batch:
        _executor.submit(send_to_user, *item)

@event.listens_for(Session, "after_rollback")
def _discard_notifications(session):
    session.info.pop("_pending_push_notifications", None)
