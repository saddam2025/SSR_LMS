import re
from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    ActiveSession, CommunicationCampaign, CommunicationDelivery, Course, Enrollment,
    Notification, ParentStudent, StudentGroup, StudentGroupMembership, StudentProfile, User,
    LessonProgress, QuizAttempt, HomeworkSubmission, Subscription, Device, SupportTicket,
)
from ..permissions import ALLOWED_ROLES
from ..request_context import audit, require_role, template_context as ctx
from ..security import check_csrf, hash_password
from ..services.template_rendering import render_template
from ..services.user_admin import import_student_rows, row_value, set_student_group, validate_admin_password, revoke_user_sessions
from ..services.reports import student_performance_rows

router = APIRouter()


@router.get("/admin/users", response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    users = db.query(User).order_by(User.id.desc()).all()
    parents = [x for x in users if x.role == "parent"]
    students = [x for x in users if x.role == "student"]
    links = db.query(ParentStudent).all()
    return render_template("admin_users.html", ctx(request, db, users=users, parents=parents, students=students, parent_links=links))


@router.post("/admin/users")
def admin_user_create(request: Request, name: str = Form(...), email: str = Form(...), role: str = Form("student"), password: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    role = role.strip().lower()
    if role not in ALLOWED_ROLES or role not in {"student", "parent", "content_manager", "support", "accounting", "admin", "super_admin"}:
        raise HTTPException(400, "دور المستخدم غير مسموح")
    email = email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email): raise HTTPException(400, "البريد الإلكتروني غير صالح")
    if db.query(User).filter(func.lower(User.email) == email).first(): raise HTTPException(409, "البريد مستخدم بالفعل")
    validate_admin_password(password)
    target = User(name=name.strip()[:120], email=email, password_hash=hash_password(password), role=role, is_active=True)
    db.add(target); db.commit(); audit(db, request, u, "user_created", {"target_user": target.id, "role": role})
    return RedirectResponse("/admin/users", 303)


@router.post("/admin/users/{user_id}/reset-password")
def admin_user_reset_password(user_id: int, request: Request, new_password: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    target = db.get(User, user_id)
    if not target: raise HTTPException(404)
    validate_admin_password(new_password)
    target.password_hash = hash_password(new_password)
    revoke_user_sessions(db, target.id)
    db.commit(); audit(db, request, admin, "admin_password_reset", {"target_user": target.id})
    return RedirectResponse("/admin/users", 303)


@router.post("/admin/users/{user_id}/reset-mfa")
def admin_user_reset_mfa(user_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    target = db.get(User, user_id)
    if not target: raise HTTPException(404)
    if target.id == admin.id: raise HTTPException(400, "لا يمكن إعادة تعيين MFA لحساب المدير الحالي من هذه الصفحة")
    target.mfa_secret = None; target.mfa_enabled = False
    revoke_user_sessions(db, target.id)
    db.commit(); audit(db, request, admin, "admin_mfa_reset", {"target_user": target.id})
    return RedirectResponse("/admin/users", 303)


@router.get("/admin/students", response_class=HTMLResponse)
def admin_students(request: Request, page: int = 1, q: str = "", db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    page_size = 100
    page = max(1, page)
    q = " ".join((q or "").strip().split())[:120]
    base_query = db.query(User).filter(User.role == "student")
    if q:
        like = f"%{q}%"
        base_query = base_query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    filtered_total = base_query.count()
    pages = max(1, (filtered_total + page_size - 1) // page_size)
    page = min(page, pages)
    students = base_query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    student_ids = [student.id for student in students]
    courses = db.query(Course).order_by(Course.title).all()
    groups = db.query(StudentGroup).filter(StudentGroup.active == True).order_by(StudentGroup.grade, StudentGroup.name).all()
    enrollments = db.query(Enrollment).filter(Enrollment.user_id.in_(student_ids)).all() if student_ids else []
    by_student = {}
    for enrollment in enrollments:
        by_student.setdefault(enrollment.user_id, []).append(enrollment)
    profiles = {profile.user_id: profile for profile in db.query(StudentProfile).filter(StudentProfile.user_id.in_(student_ids)).all()} if student_ids else {}
    membership_rows = db.query(StudentGroupMembership).filter(StudentGroupMembership.user_id.in_(student_ids)).all() if student_ids else []
    group_by_student = {membership.user_id: membership.group_id for membership in membership_rows}
    group_map = {group.id: group for group in groups}
    student_total = db.query(User).filter(User.role == "student").count()
    active_total = db.query(User).filter(User.role == "student", User.is_active == True).count()
    grouped_total = db.query(StudentGroupMembership).join(User, User.id == StudentGroupMembership.user_id).filter(User.role == "student").count()
    import_summary = request.session.pop("student_import_summary", None)
    return render_template("admin_students.html", ctx(
        request, db, students=students, courses=courses, groups=groups,
        group_by_student=group_by_student, group_map=group_map, by_student=by_student,
        profiles=profiles, import_summary=import_summary, student_total=student_total,
        active_total=active_total, grouped_total=grouped_total, ungrouped_total=max(0, student_total-grouped_total),
        page=page, pages=pages, q=q, filtered_total=filtered_total, page_size=page_size,
    ))


@router.post("/admin/students/import")
async def admin_students_import(request: Request, file: UploadFile = File(...), default_password: str = Form(...), group_id: int = Form(0), course_id: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    validate_admin_password(default_password, default=True)
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024: raise HTTPException(413, "الملف أكبر من 5MB")
    rows = import_student_rows(raw, file.filename or "")
    created = updated = skipped = 0; errors = []
    target_group = db.get(StudentGroup, group_id) if group_id else None
    target_course = db.get(Course, course_id) if course_id else None
    for idx, row in enumerate(rows, start=2):
        name = row_value(row, "name", "student_name", "الاسم", "اسم الطالب")[:120]
        email = row_value(row, "email", "البريد", "البريد الإلكتروني").lower()
        phone = row_value(row, "phone", "mobile", "الهاتف", "رقم الهاتف")[:30]
        grade = row_value(row, "grade", "الصف")[:80]
        school = row_value(row, "school", "المدرسة")[:180]
        if not name or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            skipped += 1; errors.append(f"صف {idx}: اسم أو بريد غير صالح"); continue
        student = db.query(User).filter(func.lower(User.email) == email).first()
        if student and student.role != "student":
            skipped += 1; errors.append(f"صف {idx}: البريد مستخدم لحساب غير طالب"); continue
        if not student:
            student = User(name=name, email=email, password_hash=hash_password(default_password), role="student", is_active=True); db.add(student); db.flush(); created += 1
        else:
            student.name = name; updated += 1
        profile = db.query(StudentProfile).filter_by(user_id=student.id).first()
        if not profile:
            profile = StudentProfile(user_id=student.id); db.add(profile)
        if phone: profile.phone = phone
        if grade: profile.grade = grade
        if school: profile.school = school
        if target_group: set_student_group(db, student.id, target_group.id)
        if target_course:
            enrollment = db.query(Enrollment).filter_by(user_id=student.id, course_id=target_course.id).first()
            if enrollment: enrollment.active = True
            else: db.add(Enrollment(user_id=student.id, course_id=target_course.id, active=True))
    db.commit(); audit(db, request, u, "students_bulk_imported", {"created": created, "updated": updated, "skipped": skipped, "rows": len(rows), "group_id": group_id, "course_id": course_id})
    request.session["student_import_summary"] = {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:8]}
    return RedirectResponse("/admin/students", 303)


@router.post("/admin/students/bulk")
def admin_students_bulk(request: Request, student_ids: list[int] = Form(default=[]), action: str = Form(...), group_id: int = Form(0), course_id: int = Form(0), title: str = Form(""), body: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    ids = list(dict.fromkeys(int(x) for x in student_ids))[:1000]
    students = db.query(User).filter(User.id.in_(ids or [-1]), User.role == "student").all()
    if not students: raise HTTPException(400, "اختر طالبًا واحدًا على الأقل")
    if action == "group":
        for student in students: set_student_group(db, student.id, group_id or None)
    elif action == "course":
        if not db.get(Course, course_id): raise HTTPException(404, "الكورس غير موجود")
        for student in students:
            enrollment = db.query(Enrollment).filter_by(user_id=student.id, course_id=course_id).first()
            if enrollment: enrollment.active = True
            else: db.add(Enrollment(user_id=student.id, course_id=course_id, active=True))
    elif action in {"activate", "deactivate"}:
        active = action == "activate"
        for student in students:
            student.is_active = active
            if not active: revoke_user_sessions(db, student.id)
    elif action == "notify":
        title = title.strip()[:180] or "رسالة من منصة المستشار"; body = body.strip()
        if not body: raise HTTPException(400, "نص الرسالة مطلوب")
        campaign = CommunicationCampaign(created_by=u.id, title=title, body=body, audience_type="selected_students", audience_value=",".join(str(x.id) for x in students), channels="in_app", recipient_count=len(students)); db.add(campaign); db.flush(); now = datetime.utcnow()
        for student in students:
            db.add(Notification(user_id=student.id, title=title, body=body, kind="info")); db.add(CommunicationDelivery(campaign_id=campaign.id, user_id=student.id, channel="in_app", status="sent", detail="عملية جماعية V20", sent_at=now))
    else:
        raise HTTPException(400, "إجراء غير صالح")
    db.commit(); audit(db, request, u, "students_bulk_action", {"action": action, "count": len(students), "group_id": group_id, "course_id": course_id})
    return RedirectResponse("/admin/students", 303)


@router.post("/admin/students/{student_id}/enroll")
def admin_enroll_student(student_id: int, request: Request, course_id: int = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    student = db.get(User, student_id); course = db.get(Course, course_id)
    if not student or student.role != "student" or not course: raise HTTPException(404)
    enrollment = db.query(Enrollment).filter_by(user_id=student_id, course_id=course_id).first()
    if enrollment: enrollment.active = True
    else: db.add(Enrollment(user_id=student_id, course_id=course_id, active=True))
    db.commit(); audit(db, request, u, "student_enrolled", {"student_id": student_id, "course_id": course_id})
    return RedirectResponse("/admin/students", 303)


@router.post("/admin/students/{student_id}/toggle")
def admin_toggle_student(student_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    student = db.get(User, student_id)
    if not student or student.role != "student": raise HTTPException(404)
    student.is_active = not student.is_active
    if not student.is_active: revoke_user_sessions(db, student.id)
    db.commit(); audit(db, request, u, "student_status_changed", {"student_id": student_id, "active": student.is_active})
    return RedirectResponse("/admin/students", 303)


@router.get("/admin/students/{student_id}", response_class=HTMLResponse)
def admin_student_360(student_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "support", "accounting", "content_manager")
    student = db.get(User, student_id)
    if not student or student.role != "student": raise HTTPException(404)
    profile = db.query(StudentProfile).filter_by(user_id=student.id).first()
    enrollments = db.query(Enrollment).filter_by(user_id=student.id).order_by(Enrollment.created_at.desc()).all()
    course_ids = [e.course_id for e in enrollments]
    courses = {c.id: c for c in db.query(Course).filter(Course.id.in_(course_ids or [-1])).all()}
    progress = db.query(LessonProgress).filter_by(user_id=student.id).order_by(LessonProgress.updated_at.desc()).limit(100).all()
    attempts = db.query(QuizAttempt).filter_by(user_id=student.id).order_by(QuizAttempt.created_at.desc()).limit(50).all()
    homework = db.query(HomeworkSubmission).filter_by(student_id=student.id).order_by(HomeworkSubmission.submitted_at.desc()).limit(50).all()
    subscriptions = db.query(Subscription).filter_by(user_id=student.id).order_by(Subscription.starts_at.desc()).all()
    devices = db.query(Device).filter_by(user_id=student.id).all()
    sessions = db.query(ActiveSession).filter_by(user_id=student.id).order_by(ActiveSession.created_at.desc()).limit(20).all()
    tickets = db.query(SupportTicket).filter_by(user_id=student.id).order_by(SupportTicket.updated_at.desc()).limit(20).all()
    completed = sum(1 for p in progress if p.completed)
    watched_seconds = sum(int(p.watched_seconds or 0) for p in progress)
    submitted_attempts = [a for a in attempts if a.status == "submitted"]
    quiz_avg = round(sum(float(a.score or 0) for a in submitted_attempts) / len(submitted_attempts), 1) if submitted_attempts else 0
    metrics = {"courses": len(enrollments), "completed_lessons": completed, "watched_minutes": watched_seconds // 60,
               "quiz_avg": quiz_avg, "open_tickets": sum(1 for t in tickets if t.status not in {"resolved", "closed"})}
    analytics = next((r for r in student_performance_rows(db) if r["student"].id == student.id), None)
    return render_template("admin_student_360.html", ctx(request, db, student=student, profile=profile, enrollments=enrollments,
        courses=courses, progress=progress, attempts=attempts, homework=homework, subscriptions=subscriptions,
        devices=devices, sessions=sessions, tickets=tickets, metrics=metrics, analytics=analytics))
