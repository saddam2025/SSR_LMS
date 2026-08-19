from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..models import ActiveSession, HomeworkSubmission, LessonProgress, QuizAttempt, StudentAttendance, StudentStreak


def student_last_activity(db: Session, user_id: int):
    values = [
        db.query(func.max(ActiveSession.last_seen_at)).filter(ActiveSession.user_id == user_id).scalar(),
        db.query(func.max(LessonProgress.updated_at)).filter(LessonProgress.user_id == user_id).scalar(),
        db.query(func.max(QuizAttempt.created_at)).filter(QuizAttempt.user_id == user_id).scalar(),
        db.query(func.max(HomeworkSubmission.submitted_at)).filter(HomeworkSubmission.student_id == user_id).scalar(),
    ]
    return max((value for value in values if value is not None), default=None)


def student_last_activity_map(db: Session, user_ids: list[int] | set[int] | None = None):
    result = {}
    scoped = [int(x) for x in (user_ids or []) if x]
    if user_ids is not None and not scoped:
        return result

    def keep(uid, dt):
        if uid and dt and (uid not in result or dt > result[uid]):
            result[uid] = dt

    specs = (
        (ActiveSession, ActiveSession.user_id, ActiveSession.last_seen_at),
        (LessonProgress, LessonProgress.user_id, LessonProgress.updated_at),
        (QuizAttempt, QuizAttempt.user_id, QuizAttempt.created_at),
        (HomeworkSubmission, HomeworkSubmission.student_id, HomeworkSubmission.submitted_at),
    )
    for _model, uid_col, dt_col in specs:
        q = db.query(uid_col, func.max(dt_col))
        if user_ids is not None:
            q = q.filter(uid_col.in_(scoped))
        for row in q.group_by(uid_col).all():
            keep(row[0], row[1])
    return result


def student_weekly_attendance(db: Session, user_id: int, days: int = 7):
    today = datetime.utcnow().date()
    start = today - timedelta(days=max(1, days) - 1)
    date_keys = [(start + timedelta(days=i)).isoformat() for i in range((today - start).days + 1)]
    activity_dates = set()
    recent_activity = []
    def add_dt(dt):
        if dt and start <= dt.date() <= today:
            activity_dates.add(dt.date().isoformat())
            recent_activity.append(dt)
    since = datetime.combine(start, datetime.min.time())
    for (dt,) in db.query(LessonProgress.updated_at).filter(LessonProgress.user_id == user_id, LessonProgress.updated_at >= since).all(): add_dt(dt)
    for (dt,) in db.query(QuizAttempt.created_at).filter(QuizAttempt.user_id == user_id, QuizAttempt.created_at >= since).all(): add_dt(dt)
    for (dt,) in db.query(HomeworkSubmission.submitted_at).filter(HomeworkSubmission.student_id == user_id, HomeworkSubmission.submitted_at >= since).all(): add_dt(dt)
    for (dt,) in db.query(ActiveSession.last_seen_at).filter(ActiveSession.user_id == user_id, ActiveSession.last_seen_at >= since).all(): add_dt(dt)
    manual = {a.attendance_date: a for a in db.query(StudentAttendance).filter(StudentAttendance.user_id == user_id, StudentAttendance.attendance_date.in_(date_keys)).all()}
    rows = []
    for key in date_keys:
        mark = manual.get(key)
        status = mark.status if mark else ("present" if key in activity_dates else "absent")
        rows.append({"date": key, "status": status, "source": mark.source if mark else ("activity" if key in activity_dates else "auto"), "note": mark.note if mark else ""})
    present = sum(r["status"] == "present" for r in rows)
    absent = sum(r["status"] == "absent" for r in rows)
    excused = sum(r["status"] == "excused" for r in rows)
    streak = db.query(StudentStreak).filter_by(user_id=user_id).first()
    last = max(recent_activity) if recent_activity else student_last_activity(db, user_id)
    inactive_days = max(0, (datetime.utcnow().date() - last.date()).days) if last else 999
    return {"rows": rows, "present": present, "absent": absent, "excused": excused, "rate": round(present / max(1, len(rows)) * 100), "streak": streak, "inactive_days": inactive_days, "last_activity": last}
