"""Learning runtime domain helpers extracted in V71.

This module is intentionally application-module independent so routers can use
learning access, completion, points, and playback validation without importing
app.main.
"""
import os, re, secrets
from urllib.parse import urlparse
from sqlalchemy.orm import Session
from fastapi import HTTPException
from ..access import authorized_for_course, content_schedule_allows_bulk, lesson_access_state, lesson_unlocked
from ..models import (
    Course, CourseCompletionPolicy, CourseCertificate, Homework, HomeworkSubmission,
    Lesson, LessonProgress, PointLedger, Quiz, QuizAttempt,
)
from ..services.courses import validated_video_url as _service_validated_video_url


def award_points(db: Session, user_id: int, points: int, reason: str, ref_type: str = "", ref_id: int | None = None):
    if ref_type and ref_id is not None:
        exists = db.query(PointLedger).filter_by(user_id=user_id, reason=reason, ref_type=ref_type, ref_id=ref_id).first()
        if exists:
            return
    db.add(PointLedger(user_id=user_id, points=points, reason=reason, ref_type=ref_type, ref_id=ref_id))
    db.flush()


def course_completion_status(db: Session, user_id: int, course_id: int) -> dict:
    course = db.get(Course, course_id)
    policy = db.query(CourseCompletionPolicy).filter_by(course_id=course_id).first() or CourseCompletionPolicy(course_id=course_id)

    # --- Lessons: one query for lessons, one batched schedule check, one count query ---
    all_lessons = db.query(Lesson).filter_by(course_id=course_id, published=True).all()
    allowed_lesson_ids = content_schedule_allows_bulk(db, "lesson", [x.id for x in all_lessons])
    lessons = [x for x in all_lessons if x.id in allowed_lesson_ids]
    lesson_ids = [x.id for x in lessons]
    completed = db.query(LessonProgress).filter(
        LessonProgress.user_id == user_id,
        LessonProgress.lesson_id.in_(lesson_ids or [-1]),
        LessonProgress.completed == True,
    ).count()
    lesson_pct = round((completed / len(lessons) * 100), 1) if lessons else 100.0

    # --- Quizzes: one query for quizzes, one batched schedule check, one query for all attempts ---
    all_quizzes = db.query(Quiz).filter_by(course_id=course_id, published=True).all()
    allowed_quiz_ids = content_schedule_allows_bulk(db, "quiz", [x.id for x in all_quizzes])
    quizzes = [x for x in all_quizzes if x.id in allowed_quiz_ids]
    quiz_ids = [x.id for x in quizzes]
    attempts = db.query(QuizAttempt).filter(
        QuizAttempt.user_id == user_id,
        QuizAttempt.quiz_id.in_(quiz_ids or [-1]),
        QuizAttempt.status == "submitted",
    ).all()
    attempts_by_quiz: dict[int, list] = {}
    for a in attempts:
        attempts_by_quiz.setdefault(a.quiz_id, []).append(a)
    quiz_scores = []
    for q in quizzes:
        vals = [(a.score / a.total * 100) for a in attempts_by_quiz.get(q.id, []) if a.total]
        if vals:
            quiz_scores.append(max(vals))
    quiz_avg = round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else 0.0

    # --- Homeworks: one query for homeworks, one batched schedule check, one query for all submissions ---
    all_homeworks = db.query(Homework).filter_by(course_id=course_id, published=True).all()
    allowed_hw_ids = content_schedule_allows_bulk(db, "homework", [x.id for x in all_homeworks])
    homeworks = [x for x in all_homeworks if x.id in allowed_hw_ids]
    hw_ids = [x.id for x in homeworks]
    submissions = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.homework_id.in_(hw_ids or [-1]),
        HomeworkSubmission.student_id == user_id,
    ).all()
    submission_by_hw = {s.homework_id: s for s in submissions}
    homework_scores = []
    for h in homeworks:
        sub = submission_by_hw.get(h.id)
        if sub and sub.status == "graded" and sub.score is not None:
            homework_scores.append(float(sub.score))
    homework_avg = round(sum(homework_scores) / len(homework_scores), 1) if homework_scores else 0.0

    lessons_ok = (not policy.require_all_lessons) or completed == len(lessons)
    quizzes_ok = (not policy.require_quizzes) or (len(quizzes) > 0 and len(quiz_scores) == len(quizzes) and quiz_avg >= policy.minimum_quiz_average)
    homeworks_ok = (not policy.require_homeworks) or (len(homeworks) > 0 and len(homework_scores) == len(homeworks) and homework_avg >= policy.minimum_homework_average)
    complete = bool(lessons_ok and quizzes_ok and homeworks_ok)
    components = [lesson_pct]
    if policy.require_quizzes: components.append(quiz_avg)
    if policy.require_homeworks: components.append(homework_avg)
    final_score = round(sum(components) / len(components), 1) if components else lesson_pct
    cert = db.query(CourseCertificate).filter_by(user_id=user_id, course_id=course_id).first()
    return {"course": course, "policy": policy, "lesson_pct": lesson_pct, "completed_lessons": completed,
            "total_lessons": len(lessons), "quiz_avg": quiz_avg, "quiz_done": len(quiz_scores), "quiz_total": len(quizzes),
            "homework_avg": homework_avg, "homework_done": len(homework_scores), "homework_total": len(homeworks),
            "complete": complete, "final_score": final_score, "certificate": cert}


def issue_course_certificate(db: Session, user_id: int, course_id: int) -> CourseCertificate | None:
    status = course_completion_status(db, user_id, course_id)
    if not status["complete"] or not status["policy"].certificate_enabled:
        return None
    cert = db.query(CourseCertificate).filter_by(user_id=user_id, course_id=course_id).first()
    if cert:
        if cert.revoked_at is None:
            cert.final_score = status["final_score"]
            db.commit()
            return cert
        return None
    cert = CourseCertificate(user_id=user_id, course_id=course_id, verification_code=secrets.token_urlsafe(24), final_score=status["final_score"])
    db.add(cert); db.commit(); db.refresh(cert)
    return cert


def direct_video_proxy_enabled(is_production: bool | None = None) -> bool:
    if is_production is None:
        is_production = os.getenv("ENV") == "production"
    flag = os.getenv("ALLOW_DIRECT_VIDEO_PROXY", "false").strip().lower()
    return (not is_production) or flag in {"1", "true", "yes", "on"}


def safe_range_header(value: str | None) -> str:
    if not value:
        return ""
    clean = value.strip()
    if len(clean) > 80 or not re.fullmatch(r"bytes=(?:\d+-\d*|-\d+)", clean):
        raise HTTPException(416, "نطاق الفيديو غير صالح")
    return clean


def validated_video_url(value: str, *, is_production: bool | None = None) -> str:
    value = _service_validated_video_url(value)
    if is_production is None:
        is_production = os.getenv("ENV") == "production"
    try:
        path = (urlparse(value or "").path or "").lower()
    except Exception:
        path = ""
    direct = path.endswith((".mp4", ".webm"))
    allow_direct = os.getenv("ALLOW_DIRECT_VIDEO_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"}
    if is_production and direct and not allow_direct:
        raise HTTPException(400, "روابط MP4/WebM الخام غير مسموحة في Production. استخدم مزود Streaming/DRM معتمدًا.")
    return value