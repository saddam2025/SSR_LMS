from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import (
    User, Enrollment, Lesson, LessonProgress, LessonDripRule, LessonAccessOverride,
    ContentSchedule, LessonUnitAssignment, QuizUnitAssignment, HomeworkUnitAssignment,
    ContentUnit,
)

STAFF_CONTENT_ROLES = {"super_admin", "admin", "content_manager"}


def authorized_for_course(db: Session, user: User, course_id: int, now: datetime | None = None) -> bool:
    if user.role in STAFF_CONTENT_ROLES:
        return True
    now = now or datetime.utcnow()
    enrollment = db.query(Enrollment).filter_by(user_id=user.id, course_id=course_id, active=True).first()
    if not enrollment:
        return False
    return not (enrollment.expires_at and enrollment.expires_at <= now)


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
    return db.query(ContentSchedule).filter(
        ContentSchedule.content_type == content_type,
        ContentSchedule.content_id == content_id,
    ).first()


def content_schedule_allows(db: Session, content_type: str, content_id: int, now: datetime | None = None) -> bool:
    now = now or datetime.utcnow()
    if not schedule_allows(target_schedule(db, content_type, content_id), now):
        return False
    assignment_model = {
        "lesson": LessonUnitAssignment,
        "quiz": QuizUnitAssignment,
        "homework": HomeworkUnitAssignment,
    }.get(content_type)
    id_field = {"lesson": "lesson_id", "quiz": "quiz_id", "homework": "homework_id"}.get(content_type)
    if assignment_model and id_field:
        assignment = db.query(assignment_model).filter(getattr(assignment_model, id_field) == content_id).first()
        if assignment:
            unit = db.get(ContentUnit, assignment.unit_id)
            if not unit or not unit.published or not schedule_allows(target_schedule(db, "unit", unit.id), now):
                return False
    return True


def content_schedule_allows_bulk(db: Session, content_type: str, content_ids: list[int], now: datetime | None = None) -> set[int]:
    """Batched equivalent of calling content_schedule_allows() once per id.

    Same semantics, but issues a constant number of queries instead of 1-2 per
    content item. Used by course_completion_status(), which was previously
    re-checking schedules per lesson/quiz/homework (80-100+ queries per call on a
    mid-sized course).
    """
    now = now or datetime.utcnow()
    if not content_ids:
        return set()

    schedules = db.query(ContentSchedule).filter(
        ContentSchedule.content_type == content_type,
        ContentSchedule.content_id.in_(content_ids),
    ).all()
    schedule_by_id = {s.content_id: s for s in schedules}
    allowed_direct = {cid for cid in content_ids if schedule_allows(schedule_by_id.get(cid), now)}

    assignment_model = {
        "lesson": LessonUnitAssignment,
        "quiz": QuizUnitAssignment,
        "homework": HomeworkUnitAssignment,
    }.get(content_type)
    id_field = {"lesson": "lesson_id", "quiz": "quiz_id", "homework": "homework_id"}.get(content_type)
    if not assignment_model or not id_field or not allowed_direct:
        return allowed_direct

    assignments = db.query(assignment_model).filter(getattr(assignment_model, id_field).in_(allowed_direct)).all()
    content_to_unit = {getattr(a, id_field): a.unit_id for a in assignments}
    unit_ids = {uid for uid in content_to_unit.values() if uid is not None}
    if not unit_ids:
        return allowed_direct

    units = {u.id: u for u in db.query(ContentUnit).filter(ContentUnit.id.in_(unit_ids)).all()}
    unit_schedules = db.query(ContentSchedule).filter(
        ContentSchedule.content_type == "unit",
        ContentSchedule.content_id.in_(unit_ids),
    ).all()
    unit_schedule_by_id = {s.content_id: s for s in unit_schedules}

    result = set()
    for cid in allowed_direct:
        unit_id = content_to_unit.get(cid)
        if unit_id is None:
            # No unit assignment for this item -> schedule check alone governs it,
            # matching content_schedule_allows()'s behavior.
            result.add(cid)
            continue
        unit = units.get(unit_id)
        if unit and unit.published and schedule_allows(unit_schedule_by_id.get(unit_id), now):
            result.add(cid)
    return result


def lesson_access_state(db: Session, user: User, lesson: Lesson, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    if user.role in STAFF_CONTENT_ROLES:
        return {"unlocked": True, "reason": "صلاحية إدارية", "available_at": None, "mode": "staff"}
    override = db.query(LessonAccessOverride).filter_by(user_id=user.id, lesson_id=lesson.id).first()
    if override and (not override.expires_at or override.expires_at > now):
        return {
            "unlocked": override.action == "unlock",
            "reason": "فتح يدوي من الإدارة" if override.action == "unlock" else "مغلق يدويًا من الإدارة",
            "available_at": override.expires_at,
            "mode": "override",
        }
    rule = db.query(LessonDripRule).filter_by(lesson_id=lesson.id).first()
    mode = rule.mode if rule and rule.enabled else "previous"
    delay_days = max(0, int(rule.delay_days if rule else 0))
    previous_ok = True
    previous = db.query(Lesson).filter(
        Lesson.course_id == lesson.course_id,
        Lesson.published == True,
        Lesson.order_index < lesson.order_index,
    ).order_by(Lesson.order_index.desc(), Lesson.id.desc()).first()
    if mode in {"previous", "previous_and_days"} and previous:
        progress = db.query(LessonProgress).filter_by(user_id=user.id, lesson_id=previous.id).first()
        previous_ok = bool(progress and progress.completed)
    days_ok = True
    available_at = None
    if mode in {"days", "previous_and_days"}:
        enrollment = db.query(Enrollment).filter_by(user_id=user.id, course_id=lesson.course_id, active=True).first()
        if not enrollment:
            days_ok = False
        else:
            available_at = enrollment.created_at + timedelta(days=delay_days)
            days_ok = now >= available_at
    unlocked = previous_ok and days_ok
    reasons = []
    if not previous_ok:
        reasons.append("أكمل الدرس السابق أولًا")
    if not days_ok and available_at:
        reasons.append(f"يفتح بعد {delay_days} يوم من الاشتراك")
    return {
        "unlocked": unlocked,
        "reason": " • ".join(reasons) if reasons else "متاح الآن",
        "available_at": available_at,
        "mode": mode,
    }


def lesson_unlocked(db: Session, user: User, lesson: Lesson) -> bool:
    return bool(lesson_access_state(db, user, lesson)["unlocked"])