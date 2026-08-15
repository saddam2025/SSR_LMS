from datetime import datetime
from sqlalchemy.orm import Session
from ..models import ContentSchedule, RevisionTask, Lesson, Quiz, Homework


def schedule_status(schedule: ContentSchedule | None, now: datetime | None = None) -> str:
    if not schedule or not schedule.enabled:
        return "manual"
    now = now or datetime.utcnow()
    if schedule.starts_at and now < schedule.starts_at:
        return "scheduled"
    if schedule.ends_at and now >= schedule.ends_at:
        return "expired"
    return "live"


def schedule_allows(schedule: ContentSchedule | None, now: datetime | None = None) -> bool:
    return schedule_status(schedule, now) in {"manual", "live"}


def target_schedule(db: Session, content_type: str, content_id: int) -> ContentSchedule | None:
    return db.query(ContentSchedule).filter(ContentSchedule.content_type == content_type, ContentSchedule.content_id == content_id).first()


def revision_target(db: Session, task: RevisionTask):
    model = {"lesson": Lesson, "quiz": Quiz, "homework": Homework}.get(task.content_type)
    return db.get(model, task.content_id) if model and task.content_id else None


def revision_target_url(task: RevisionTask) -> str:
    if not task.content_id:
        return ""
    return {"lesson": f"/lesson/{task.content_id}", "quiz": f"/quiz/{task.content_id}", "homework": f"/homework/{task.content_id}"}.get(task.content_type, "")
