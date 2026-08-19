from datetime import datetime, timedelta
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session
from ..models import (
    User, StudentProfile, StudentAttendance, Enrollment, LiveClass,
    StudentGroupMembership, GroupLiveClassAssignment, GroupCourseAssignment,
    ActiveSession, LessonProgress, QuizAttempt, HomeworkSubmission,
)
from .student_activity import student_last_activity_map

SUPPORTED_LIVE_PROVIDERS = {"zoom", "meet", "teams", "youtube", "custom"}
LIVE_PROVIDER_HOSTS = {
    "zoom": {"zoom.us", "zoom.com"},
    "meet": {"meet.google.com"},
    "teams": {"teams.microsoft.com", "teams.live.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
}

def safe_live_url(value: str, provider: str = "custom") -> str:
    clean = value.strip()[:700]
    if not clean:
        return ""
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    provider = provider.strip().lower()
    if provider not in SUPPORTED_LIVE_PROVIDERS:
        raise HTTPException(400, "مزود الحصة غير صالح")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise HTTPException(400, "رابط الحصة يجب أن يكون HTTPS صالحًا")
    allowed = LIVE_PROVIDER_HOSTS.get(provider)
    if allowed and not any(host == h or host.endswith("." + h) for h in allowed):
        raise HTTPException(400, "رابط الحصة لا يطابق المزود المحدد")
    return clean

def student_group_id(db: Session, user_id: int):
    row=db.query(StudentGroupMembership).filter_by(user_id=user_id).first()
    return row.group_id if row else None

def group_member_ids(db: Session, group_id: int):
    return [x.user_id for x in db.query(StudentGroupMembership).filter_by(group_id=group_id).all()]

def sync_group_course(db: Session, group_id: int, course_id: int):
    """Activate a course for a whole group without an N+1 enrollment query."""
    member_ids = group_member_ids(db, group_id)
    if not member_ids:
        return 0
    existing = {
        row.user_id: row
        for row in db.query(Enrollment).filter(Enrollment.course_id == course_id, Enrollment.user_id.in_(member_ids)).all()
    }
    for row in existing.values():
        row.active = True
    missing = [uid for uid in member_ids if uid not in existing]
    if missing:
        db.add_all([Enrollment(user_id=uid, course_id=course_id, active=True) for uid in missing])
    return len(member_ids)

def live_class_group_id(db: Session, live_class_id: int):
    row=db.query(GroupLiveClassAssignment).filter_by(live_class_id=live_class_id).first()
    return row.group_id if row else None

def _activity_condition(day_start: datetime, day_end: datetime | None = None):
    def bounded(column):
        parts = [column >= day_start]
        if day_end is not None:
            parts.append(column < day_end)
        return parts
    return or_(
        exists().where(ActiveSession.user_id == User.id, *bounded(ActiveSession.last_seen_at)),
        exists().where(LessonProgress.user_id == User.id, *bounded(LessonProgress.updated_at)),
        exists().where(QuizAttempt.user_id == User.id, *bounded(QuizAttempt.created_at)),
        exists().where(HomeworkSubmission.student_id == User.id, *bounded(HomeworkSubmission.submitted_at)),
    )


def _activity_ids_for_day(db: Session, day_start: datetime, day_end: datetime, user_ids: list[int] | None = None) -> set[int]:
    """Return students with real platform activity during the selected UTC day."""
    ids: set[int] = set()
    scope = [int(x) for x in (user_ids or []) if x]
    if user_ids is not None and not scope:
        return ids
    for model_col, user_col in (
        (ActiveSession.last_seen_at, ActiveSession.user_id),
        (LessonProgress.updated_at, LessonProgress.user_id),
        (QuizAttempt.created_at, QuizAttempt.user_id),
        (HomeworkSubmission.submitted_at, HomeworkSubmission.student_id),
    ):
        q = db.query(user_col).filter(model_col >= day_start, model_col < day_end)
        if user_ids is not None:
            q = q.filter(user_col.in_(scope))
        rows = q.distinct().all()
        ids.update(int(row[0]) for row in rows if row[0])
    return ids


def attendance_page(db: Session, target_date: str, status: str = "all", page: int = 1, page_size: int = 100):
    """Set-based, paginated attendance suitable for tens of thousands of students.

    Manual marks override automatically detected activity. Metrics and filtering are
    computed by SQL; only the visible page is materialized in Python.
    """
    page_size = max(25, min(int(page_size or 100), 200))
    page = max(1, int(page or 1))
    day_start = datetime.strptime(target_date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)
    activity_today = _activity_condition(day_start, day_end)
    manual_exists = exists().where(
        StudentAttendance.user_id == User.id,
        StudentAttendance.attendance_date == target_date,
    )

    active_filter = (User.role == "student", User.is_active == True)
    total = db.query(func.count(User.id)).filter(*active_filter).scalar() or 0
    manual_counts = dict(
        db.query(StudentAttendance.status, func.count(StudentAttendance.id))
        .join(User, User.id == StudentAttendance.user_id)
        .filter(*active_filter, StudentAttendance.attendance_date == target_date)
        .group_by(StudentAttendance.status)
        .all()
    )
    auto_present = db.query(func.count(User.id)).filter(*active_filter, ~manual_exists, activity_today).scalar() or 0
    present = int(manual_counts.get("present", 0)) + int(auto_present)
    excused = int(manual_counts.get("excused", 0))
    absent = max(0, int(total) - present - excused)

    inactive_cutoff = datetime.utcnow() - timedelta(days=3)
    inactive = db.query(func.count(User.id)).filter(*active_filter, ~_activity_condition(inactive_cutoff, None)).scalar() or 0
    metrics = {
        "students": int(total),
        "present": present,
        "absent": absent,
        "excused": excused,
        "inactive": int(inactive),
    }

    q = (
        db.query(User)
        .outerjoin(
            StudentAttendance,
            and_(StudentAttendance.user_id == User.id, StudentAttendance.attendance_date == target_date),
        )
        .filter(*active_filter)
    )
    if status == "present":
        q = q.filter(or_(StudentAttendance.status == "present", and_(StudentAttendance.id == None, activity_today)))
    elif status == "excused":
        q = q.filter(StudentAttendance.status == "excused")
    elif status == "absent":
        q = q.filter(or_(StudentAttendance.status == "absent", and_(StudentAttendance.id == None, ~activity_today)))

    filtered_total = q.count()
    pages = max(1, (filtered_total + page_size - 1) // page_size)
    page = min(page, pages)
    students = q.order_by(User.name, User.id).offset((page - 1) * page_size).limit(page_size).all()
    page_ids = [student.id for student in students]

    manual = {
        row.user_id: row
        for row in db.query(StudentAttendance).filter(
            StudentAttendance.attendance_date == target_date,
            StudentAttendance.user_id.in_(page_ids or [-1]),
        ).all()
    }
    activity_ids = _activity_ids_for_day(db, day_start, day_end, page_ids)
    last_map = student_last_activity_map(db, page_ids)
    profiles = {
        profile.user_id: profile
        for profile in db.query(StudentProfile).filter(StudentProfile.user_id.in_(page_ids or [-1])).all()
    }
    rows = []
    today = datetime.utcnow().date()
    for student in students:
        mark = manual.get(student.id)
        last = last_map.get(student.id)
        resolved_status = mark.status if mark else ("present" if student.id in activity_ids else "absent")
        rows.append({
            "student": student,
            "profile": profiles.get(student.id),
            "status": resolved_status,
            "source": mark.source if mark else ("activity" if student.id in activity_ids else "auto"),
            "note": mark.note if mark else "",
            "last_activity": last,
            "inactive_days": max(0, (today - last.date()).days) if last else 999,
        })
    return rows, metrics, page, pages, filtered_total, page_size

def attendance_rows(db: Session, target_date: str):
    """Compatibility helper used by older tests/extensions."""
    rows, _metrics, _page, _pages, _total, _page_size = attendance_page(
        db, target_date, status="all", page=1, page_size=200
    )
    # Preserve the historical helper for small callers; production route uses pagination.
    total = db.query(User).filter(User.role == "student", User.is_active == True).count()
    if total <= 200:
        return rows
    return rows

def student_live_classes(db: Session, user_id: int, days_before: int = 7, days_after: int = 21, course_ids: list[int] | None = None):
    now = datetime.utcnow()
    if course_ids is None:
        course_ids=[x.course_id for x in db.query(Enrollment).filter(Enrollment.user_id==user_id, Enrollment.active==True).all()]
    if not course_ids: return []
    classes=db.query(LiveClass).filter(LiveClass.course_id.in_(course_ids), LiveClass.scheduled_at >= now-timedelta(days=days_before), LiveClass.scheduled_at <= now+timedelta(days=days_after), LiveClass.status != "cancelled").order_by(LiveClass.scheduled_at).all()
    gid=student_group_id(db,user_id)
    assigned={x.live_class_id:x.group_id for x in db.query(GroupLiveClassAssignment).filter(GroupLiveClassAssignment.live_class_id.in_([c.id for c in classes] or [-1])).all()}
    return [c for c in classes if c.id not in assigned or (gid and assigned[c.id]==gid)]

def live_class_student_query(db: Session, live_class: LiveClass):
    """Set-based eligible-student query for a live class."""
    q = (
        db.query(User)
        .join(Enrollment, Enrollment.user_id == User.id)
        .filter(
            Enrollment.course_id == live_class.course_id,
            Enrollment.active == True,
            User.role == "student",
            User.is_active == True,
        )
    )
    gid = live_class_group_id(db, live_class.id)
    if gid:
        q = q.join(StudentGroupMembership, StudentGroupMembership.user_id == User.id).filter(StudentGroupMembership.group_id == gid)
    return q.distinct()


def live_class_student_ids(db: Session, live_class: LiveClass) -> list[int]:
    return [int(row[0]) for row in live_class_student_query(db, live_class).with_entities(User.id).order_by(User.id).all()]


def live_class_students(db: Session, live_class: LiveClass, *, page: int | None = None, page_size: int = 100, q: str = ""):
    query = live_class_student_query(db, live_class)
    q = " ".join((q or "").strip().split())[:120]
    if q:
        like = f"%{q}%"
        query = query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    query = query.order_by(User.name, User.id)
    if page is None:
        return query.all()
    page_size = max(25, min(int(page_size or 100), 200))
    page = max(1, int(page or 1))
    total = query.count()
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return rows, page, pages, total, page_size
