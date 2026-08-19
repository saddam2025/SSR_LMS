from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Course, Lesson, Enrollment, Quiz, QuizAttempt, Device, ActiveSession, LessonProgress, Subscription, PaymentTransaction, Homework, HomeworkSubmission, MediaAsset, SupportTicket, LiveClass, CommunicationCampaign, AuditLog, ContentSchedule, CourseCertificate
from ..request_context import require_user, require_role, template_context as ctx
from ..services.template_rendering import render_template
from ..services.dashboard_experience import points_total as dashboard_points_total, level_for as dashboard_level_for, student_plan as dashboard_student_plan
from ..services.student_activity import student_weekly_attendance
from ..services.community import student_live_classes
from ..services.reports import student_performance_rows, performance_candidate_student_ids
from ..services.academic_content import schedule_status
router=APIRouter()

@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    if u.role in {"super_admin", "admin"}:
        return RedirectResponse("/admin", 302)
    if u.role == "content_manager":
        return RedirectResponse("/teacher", 302)
    if u.role == "support":
        return RedirectResponse("/support", 302)
    if u.role == "accounting":
        return RedirectResponse("/admin/commerce", 302)
    if u.role == "parent":
        return RedirectResponse("/parent", 302)
    enrollments = db.query(Enrollment).filter(Enrollment.user_id == u.id, Enrollment.active == True).all()
    course_ids = [e.course_id for e in enrollments]
    course_map = {c.id: c for c in db.query(Course).filter(Course.id.in_(course_ids)).all()} if course_ids else {}
    courses = [course_map[e.course_id] for e in enrollments if e.course_id in course_map]
    attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == u.id).order_by(QuizAttempt.id.desc()).limit(10).all()
    devices = db.query(Device).filter_by(user_id=u.id).order_by(Device.last_seen_at.desc()).all()
    avg_progress = round(sum(e.progress for e in enrollments) / len(enrollments)) if enrollments else 0
    pts = dashboard_points_total(db, u.id); level_name, level_no = dashboard_level_for(pts)
    plan = dashboard_student_plan(db, u.id, enrollments=enrollments, courses=course_map)
    attendance = student_weekly_attendance(db, u.id, 7)
    activity_alert = attendance["inactive_days"] >= 3 or attendance["present"] < 2
    live_classes=student_live_classes(db,u.id,days_before=0,days_after=14,course_ids=course_ids)
    certificates = db.query(CourseCertificate).filter_by(user_id=u.id).filter(CourseCertificate.revoked_at.is_(None)).order_by(CourseCertificate.issued_at.desc()).all()
    return render_template("student_dashboard.html", ctx(request, db, enrollments=enrollments, courses=courses, attempts=attempts, devices=devices, avg_progress=avg_progress, points=pts, level_name=level_name, level_no=level_no, study_plan=plan, attendance=attendance, activity_alert=activity_alert, live_classes=live_classes[:3], certificates=certificates))

@router.get("/teacher", response_class=HTMLResponse)
def teacher_dashboard(request: Request, db: Session = Depends(get_db)):
    """Content workspace for the platform teacher/content team in this single-teacher LMS."""
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    courses = db.query(Course).order_by(Course.id.desc()).all()
    course_ids = [c.id for c in courses]
    recent_lessons = db.query(Lesson).order_by(Lesson.id.desc()).limit(8).all()
    recent_quizzes = db.query(Quiz).order_by(Quiz.id.desc()).limit(8).all()
    pending_homework = db.query(HomeworkSubmission).filter(HomeworkSubmission.status == "submitted", HomeworkSubmission.graded_at.is_(None)).count()
    schedules = db.query(ContentSchedule).all()
    schedule_map = {f"{x.content_type}:{x.content_id}": x for x in schedules}
    now_schedule = datetime.utcnow()
    schedule_stats = {
        "scheduled": sum(1 for x in schedules if schedule_status(x, now_schedule) == "scheduled"),
        "live": sum(1 for x in schedules if schedule_status(x, now_schedule) == "live"),
        "expired": sum(1 for x in schedules if schedule_status(x, now_schedule) == "expired"),
    }
    stats = {
        "courses": len(courses),
        "published_courses": sum(1 for c in courses if c.published),
        "lessons": db.query(Lesson).count(),
        "published_lessons": db.query(Lesson).filter(Lesson.published == True).count(),
        "quizzes": db.query(Quiz).count(),
        "published_quizzes": db.query(Quiz).filter(Quiz.published == True).count(),
        "assets": db.query(MediaAsset).count(),
        "pending_homework": pending_homework,
    }
    return render_template("teacher_dashboard.html", ctx(request, db, user=u, stats=stats, courses=courses, recent_lessons=recent_lessons, recent_quizzes=recent_quizzes))

@router.get("/teacher/assessment", response_class=HTMLResponse)
def teacher_assessment_center(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    now = datetime.utcnow()

    pending_q = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.status.in_(["submitted", "resubmitted"]),
        HomeworkSubmission.graded_at.is_(None),
    )
    pending_count = pending_q.count()
    pending = pending_q.order_by(HomeworkSubmission.submitted_at.asc()).limit(100).all()
    revision_count = db.query(func.count(HomeworkSubmission.id)).filter(HomeworkSubmission.status == "revision_requested").scalar() or 0
    late_count = (
        db.query(func.count(HomeworkSubmission.id))
        .join(Homework, Homework.id == HomeworkSubmission.homework_id)
        .filter(Homework.due_at.isnot(None), HomeworkSubmission.submitted_at > Homework.due_at)
        .scalar() or 0
    )
    avg_score = float(
        db.query(func.coalesce(func.avg(HomeworkSubmission.score), 0))
        .filter(HomeworkSubmission.score.isnot(None), HomeworkSubmission.graded_at.isnot(None))
        .scalar() or 0
    )
    avg_score = round(avg_score, 1)

    # Missing submissions are derived in SQL instead of materializing every active
    # enrollment and every submission in Python. Only the first 100 rows are rendered.
    missing_q = (
        db.query(User, Homework, Course)
        .join(Enrollment, Enrollment.user_id == User.id)
        .join(Homework, Homework.course_id == Enrollment.course_id)
        .join(Course, Course.id == Homework.course_id)
        .outerjoin(
            HomeworkSubmission,
            and_(
                HomeworkSubmission.homework_id == Homework.id,
                HomeworkSubmission.student_id == User.id,
            ),
        )
        .filter(
            User.role == "student",
            User.is_active == True,
            Enrollment.active == True,
            Homework.published == True,
            Homework.due_at.isnot(None),
            Homework.due_at < now,
            HomeworkSubmission.id.is_(None),
        )
    )
    missing_count = missing_q.count()
    missing_rows = [
        {"student": student, "homework": homework, "course": course}
        for student, homework, course in missing_q.order_by(Homework.due_at.desc(), User.name).limit(100).all()
    ]

    graded = (
        db.query(HomeworkSubmission)
        .filter(HomeworkSubmission.score.isnot(None))
        .order_by(HomeworkSubmission.graded_at.desc().nullslast(), HomeworkSubmission.id.desc())
        .limit(12)
        .all()
    )
    visible_submissions = pending + graded
    homework_ids = {x.homework_id for x in visible_submissions}
    student_ids = {x.student_id for x in visible_submissions}
    homework_map = {h.id: h for h in db.query(Homework).filter(Homework.id.in_(homework_ids or [-1])).all()}
    course_ids = {h.course_id for h in homework_map.values()}
    courses = {c.id: c for c in db.query(Course).filter(Course.id.in_(course_ids or [-1])).all()}
    students = {x.id: x for x in db.query(User).filter(User.id.in_(student_ids or [-1])).all()}

    # Template keeps its historical names, but KPI values now represent full-table
    # SQL counts while rendered work queues stay bounded.
    return render_template("teacher_assessment.html", ctx(
        request, db, user=u, homework_map=homework_map, students=students, courses=courses,
        pending=pending, revision=[], graded=graded, late=[],
        missing_rows=missing_rows, avg_score=avg_score,
        pending_count=int(pending_count), revision_count=int(revision_count),
        late_count=int(late_count), missing_count=int(missing_count), now=now,
    ))

@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    tomorrow = today_start + timedelta(days=1)
    soon = now + timedelta(days=7)
    month_start = now - timedelta(days=30)

    stats = {
        "users": db.query(User).count(),
        "students": db.query(User).filter(User.role=="student", User.is_active==True).count(),
        "courses": db.query(Course).count(),
        "lessons": db.query(Lesson).count(),
        "attempts": db.query(QuizAttempt).count(),
        "sessions": db.query(ActiveSession).filter(ActiveSession.revoked_at.is_(None)).count(),
        "subscriptions": db.query(Subscription).filter(Subscription.status == "active").count(),
        "completed_lessons": db.query(LessonProgress).filter(LessonProgress.completed==True).count(),
        "open_tickets": db.query(SupportTicket).filter(~SupportTicket.status.in_(["resolved","closed"])).count(),
        "paid_revenue": float(db.query(func.coalesce(func.sum(PaymentTransaction.amount), 0)).filter(PaymentTransaction.status=="paid").scalar() or 0),
        "revenue_30": float(db.query(func.coalesce(func.sum(PaymentTransaction.amount), 0)).filter(PaymentTransaction.status=="paid", PaymentTransaction.paid_at>=month_start).scalar() or 0),
        "revenue_today": float(db.query(func.coalesce(func.sum(PaymentTransaction.amount), 0)).filter(PaymentTransaction.status=="paid", PaymentTransaction.paid_at>=today_start, PaymentTransaction.paid_at<tomorrow).scalar() or 0),
        "pending_homework": db.query(HomeworkSubmission).filter(HomeworkSubmission.score.is_(None), HomeworkSubmission.status.in_(["submitted","resubmitted"])).count(),
        "expiring_subscriptions": db.query(Subscription).filter(Subscription.status=="active", Subscription.ends_at.isnot(None), Subscription.ends_at>now, Subscription.ends_at<=soon).count(),
        "pending_payments": db.query(PaymentTransaction).filter(PaymentTransaction.status=="pending").count(),
    }

    # V31 daily command center: reuse the same performance engine as the detailed reports.
    candidate_ids = performance_candidate_student_ids(db, limit=int(__import__("os").getenv("ADMIN_DASHBOARD_RISK_CANDIDATES", "400")))
    performance_rows = student_performance_rows(db, student_ids=candidate_ids)
    at_risk_students = [r for r in performance_rows if r["risk"] == "high"][:6]
    followup_students = [r for r in performance_rows if r["risk"] == "medium"][:6]

    upcoming_classes = db.query(LiveClass).filter(
        LiveClass.scheduled_at >= now,
        ~LiveClass.status.in_(["completed", "cancelled"]),
    ).order_by(LiveClass.scheduled_at.asc()).limit(6).all()
    class_course_ids = {x.course_id for x in upcoming_classes}
    class_courses = {c.id:c for c in db.query(Course).filter(Course.id.in_(class_course_ids or [-1])).all()}

    pending_submissions = db.query(HomeworkSubmission).filter(
        HomeworkSubmission.score.is_(None),
        HomeworkSubmission.status.in_(["submitted", "resubmitted"]),
    ).order_by(HomeworkSubmission.submitted_at.asc()).limit(6).all()
    submission_students = {x.student_id for x in pending_submissions}
    submission_homework_ids = {x.homework_id for x in pending_submissions}
    submission_student_map = {u.id:u for u in db.query(User).filter(User.id.in_(submission_students or [-1])).all()}
    submission_homework_map = {h.id:h for h in db.query(Homework).filter(Homework.id.in_(submission_homework_ids or [-1])).all()}

    expiring = db.query(Subscription).filter(
        Subscription.status=="active", Subscription.ends_at.isnot(None),
        Subscription.ends_at>now, Subscription.ends_at<=soon,
    ).order_by(Subscription.ends_at.asc()).limit(6).all()
    expiring_user_ids = {x.user_id for x in expiring}
    expiring_course_ids = {x.course_id for x in expiring}
    expiring_users = {u.id:u for u in db.query(User).filter(User.id.in_(expiring_user_ids or [-1])).all()}
    expiring_courses = {c.id:c for c in db.query(Course).filter(Course.id.in_(expiring_course_ids or [-1])).all()}

    urgent_tickets = db.query(SupportTicket).filter(
        ~SupportTicket.status.in_(["resolved","closed"])
    ).order_by(SupportTicket.priority.desc(), SupportTicket.updated_at.desc()).limit(6).all()
    ticket_user_ids = {x.user_id for x in urgent_tickets}
    ticket_users = {u.id:u for u in db.query(User).filter(User.id.in_(ticket_user_ids or [-1])).all()}

    recent_campaigns = db.query(CommunicationCampaign).order_by(CommunicationCampaign.created_at.desc()).limit(4).all()
    courses = db.query(Course).order_by(Course.id.desc()).all()
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(20).all()
    return render_template("admin.html", ctx(
        request, db, stats=stats, courses=courses, logs=logs, now=now,
        at_risk_students=at_risk_students, followup_students=followup_students,
        upcoming_classes=upcoming_classes, class_courses=class_courses,
        pending_submissions=pending_submissions, submission_student_map=submission_student_map, submission_homework_map=submission_homework_map,
        expiring=expiring, expiring_users=expiring_users, expiring_courses=expiring_courses,
        urgent_tickets=urgent_tickets, ticket_users=ticket_users, recent_campaigns=recent_campaigns,
    ))

