"""Course and lesson administration routes extracted in V69.

These routes keep the public HTTP contract stable while removing content-management
responsibilities from app.main. Student playback remains separate from this router.
"""
import os
from datetime import datetime
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    User, Course, Lesson, Enrollment, Quiz, MediaAsset, Homework, HomeworkSubmission,
    LessonCheckpoint, CheckpointAttempt, LessonFlashcard, OfflineLessonPolicy, OfflineGrant,
    StudyAssistantLog, LessonProgress, LessonVideoProfile, LessonDripRule, LessonAccessOverride,
    CourseCompletionPolicy, CourseCertificate
)
from ..permissions import can_manage_course
from ..security import check_csrf
from ..request_context import require_role, template_context, audit
from ..cloudflare_stream import extract_stream_uid
from ..cloudflare_upload import stream_upload_ready, max_upload_bytes as stream_max_upload_bytes
from ..storage import s3_ready
from ..services.courses import validated_video_url

router = APIRouter()

def direct_media_upload_enabled() -> bool:
    return os.getenv("DIRECT_R2_UPLOAD_ENABLED", "false").lower() in {"1", "true", "yes", "on"} and s3_ready()

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))

def render_template(name: str, context: dict, status_code: int = 200):
    request = context.get("request")
    if request is None:
        raise RuntimeError("Template context must include request")
    return Jinja2Templates.TemplateResponse(templates, request=request, name=name, context=context, status_code=status_code)

@router.post("/admin/courses")
def create_course(request: Request, title: str = Form(...), grade: str = Form(...), price: float = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = Course(title=title.strip(), grade=grade.strip(), price=max(0, price), published=False, teacher_id=None)
    db.add(c); db.commit(); audit(db, request, u, "create_course", {"course_id": c.id})
    return RedirectResponse("/admin/courses", 303)

@router.post("/admin/courses/{course_id}/toggle")
def toggle_course(course_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c: raise HTTPException(404)
    if not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    c.published = not c.published; db.commit(); audit(db, request, u, "toggle_course", {"course_id": course_id, "published": c.published})
    return RedirectResponse("/admin/courses", 303)

@router.get("/admin/course/{course_id}", response_class=HTMLResponse)
def admin_course(course_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    c = db.get(Course, course_id)
    if not c: raise HTTPException(404)
    if not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    quizzes = db.query(Quiz).filter(Quiz.course_id == c.id).all()
    assets = db.query(MediaAsset).join(Lesson, MediaAsset.lesson_id == Lesson.id).filter(Lesson.course_id == c.id).order_by(MediaAsset.id.desc()).all()
    homeworks = db.query(Homework).filter_by(course_id=c.id).order_by(Homework.id.desc()).all()
    hw_ids = [h.id for h in homeworks] or [-1]
    submissions = db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id.in_(hw_ids)).order_by(HomeworkSubmission.id.desc()).all()
    submission_student_ids = {x.student_id for x in submissions}
    students = {x.id: x for x in db.query(User).filter(User.id.in_(submission_student_ids or [-1]), User.role == "student").all()}
    lesson_map = {l.id: l for l in c.lessons}
    lesson_ids = list(lesson_map) or [-1]
    checkpoints = db.query(LessonCheckpoint).filter(LessonCheckpoint.lesson_id.in_(lesson_ids)).order_by(LessonCheckpoint.lesson_id, LessonCheckpoint.timestamp_seconds).all()
    flashcards = db.query(LessonFlashcard).filter(LessonFlashcard.lesson_id.in_(lesson_ids)).order_by(LessonFlashcard.lesson_id, LessonFlashcard.order_index).all()
    offline_policies = {x.lesson_id: x for x in db.query(OfflineLessonPolicy).filter(OfflineLessonPolicy.lesson_id.in_(lesson_ids)).all()}
    completion_policy = db.query(CourseCompletionPolicy).filter_by(course_id=c.id).first() or CourseCompletionPolicy(course_id=c.id)
    certificates_count = db.query(CourseCertificate).filter_by(course_id=c.id).filter(CourseCertificate.revoked_at.is_(None)).count()
    return render_template("admin_course.html", template_context(request, db, course=c, quizzes=quizzes, assets=assets, homeworks=homeworks, submissions=submissions, students=students, checkpoints=checkpoints, flashcards=flashcards, offline_policies=offline_policies, lesson_map=lesson_map, completion_policy=completion_policy, certificates_count=certificates_count, direct_media_upload_enabled=direct_media_upload_enabled()))

@router.post("/admin/course/{course_id}/update")
def update_course(course_id: int, request: Request, title: str = Form(...), description: str = Form(""), grade: str = Form(...), price: float = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c or not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    c.title = title.strip()[:180]; c.description = description.strip(); c.grade = grade.strip()[:50]; c.price = max(0, round(price, 2))
    db.commit(); audit(db, request, u, "course_updated", {"course_id": c.id})
    return RedirectResponse(f"/admin/course/{c.id}", 303)

@router.get("/admin/lesson/{lesson_id}/edit", response_class=HTMLResponse)
def edit_lesson_page(lesson_id: int, request: Request, student_q: str = "", db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    course = db.get(Course, lesson.course_id)
    if not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    assets = db.query(MediaAsset).filter(MediaAsset.lesson_id == lesson.id).order_by(MediaAsset.id.desc()).all()
    siblings = db.query(Lesson).filter(Lesson.course_id == course.id).order_by(Lesson.order_index, Lesson.id).all()
    video_profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson.id).first()
    drip_rule = db.query(LessonDripRule).filter_by(lesson_id=lesson.id).first()
    overrides = db.query(LessonAccessOverride).filter_by(lesson_id=lesson.id).order_by(LessonAccessOverride.updated_at.desc()).limit(20).all()
    override_users = {x.user_id: db.get(User, x.user_id) for x in overrides}
    student_q = student_q.strip()[:120]
    student_query = db.query(User).join(Enrollment, Enrollment.user_id == User.id).filter(Enrollment.course_id == course.id, Enrollment.active == True, User.role == "student", User.is_active == True)
    if student_q:
        like = f"%{student_q}%"
        student_query = student_query.filter(or_(User.name.ilike(like), User.email.ilike(like)))
    students = student_query.order_by(User.name, User.id).limit(50).all()
    return render_template("admin_lesson_edit.html", template_context(
        request, db, lesson=lesson, course=course, assets=assets, siblings=siblings,
        video_profile=video_profile, drip_rule=drip_rule, overrides=overrides,
        override_users=override_users, students=students, student_q=student_q,
        stream_uid=extract_stream_uid(lesson.video_url) or "",
        stream_upload_configured=stream_upload_ready(),
        stream_upload_max_bytes=stream_max_upload_bytes(), direct_media_upload_enabled=direct_media_upload_enabled(),
    ))

@router.post("/admin/lesson/{lesson_id}/update")
def update_lesson(lesson_id: int, request: Request, title: str = Form(...), body: str = Form(""), video_url: str = Form(""), order_index: int = Form(1), published: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    course = db.get(Course, lesson.course_id)
    if not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    clean_title = title.strip()[:180]
    if not clean_title: raise HTTPException(400, "عنوان الدرس مطلوب")
    lesson.title = clean_title
    lesson.body = body.strip()
    next_video_url = validated_video_url(video_url)
    wants_publish = published == "on"
    # A Cloudflare Stream lecture must never become visible to students before
    # provider processing has completed. This is enforced server-side rather
    # than relying on the admin UI checkbox.
    if wants_publish and extract_stream_uid(next_video_url):
        profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson.id).first()
        if not profile or profile.provider != "cloudflare" or profile.processing_status != "ready":
            raise HTTPException(409, "لا يمكن نشر المحاضرة قبل اكتمال معالجة الفيديو وظهور حالته جاهز.")
    lesson.video_url = next_video_url
    lesson.order_index = max(1, min(int(order_index), 10000))
    lesson.published = wants_publish
    db.commit()
    audit(db, request, u, "lesson_updated", {"lesson_id": lesson.id, "course_id": course.id, "order_index": lesson.order_index, "published": lesson.published})
    return RedirectResponse(f"/admin/lesson/{lesson.id}/edit", 303)

@router.post("/admin/lesson/{lesson_id}/drip-rule")
def update_lesson_drip_rule(lesson_id: int, request: Request, mode: str = Form("previous"), delay_days: int = Form(0), enabled: str = Form("on"), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    allowed = {"open", "previous", "days", "previous_and_days"}
    if mode not in allowed: raise HTTPException(400, "قاعدة فتح غير صالحة")
    rule = db.query(LessonDripRule).filter_by(lesson_id=lesson.id).first()
    if not rule:
        rule = LessonDripRule(lesson_id=lesson.id); db.add(rule)
    rule.mode = mode; rule.delay_days = max(0, min(int(delay_days), 3650)); rule.enabled = enabled.lower() in {"1","true","on","yes"}
    db.commit(); audit(db, request, u, "lesson_drip_rule_updated", {"lesson_id": lesson.id, "mode": rule.mode, "delay_days": rule.delay_days, "enabled": rule.enabled})
    return RedirectResponse(f"/admin/lesson/{lesson.id}/edit#drip-control", 303)

@router.post("/admin/lesson/{lesson_id}/access-override")
def lesson_access_override(lesson_id: int, request: Request, student_id: int = Form(...), action: str = Form("unlock"), expires_at: str = Form(""), note: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); course = db.get(Course, lesson.course_id) if lesson else None; student = db.get(User, student_id)
    if not lesson or not course or not student or student.role != "student" or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    if not db.query(Enrollment).filter_by(user_id=student.id, course_id=course.id, active=True).first(): raise HTTPException(400, "الطالب غير مشترك في الكورس")
    if action == "clear":
        row = db.query(LessonAccessOverride).filter_by(user_id=student.id, lesson_id=lesson.id).first()
        if row: db.delete(row); db.commit()
        audit(db, request, u, "lesson_access_override_cleared", {"lesson_id": lesson.id, "student_id": student.id})
        return RedirectResponse(f"/admin/lesson/{lesson.id}/edit#drip-control", 303)
    if action not in {"unlock", "lock"}: raise HTTPException(400)
    expiry = None
    if expires_at.strip():
        try: expiry = datetime.fromisoformat(expires_at.strip())
        except ValueError: raise HTTPException(400, "تاريخ انتهاء غير صالح")
    row = db.query(LessonAccessOverride).filter_by(user_id=student.id, lesson_id=lesson.id).first()
    if not row:
        row = LessonAccessOverride(user_id=student.id, lesson_id=lesson.id); db.add(row)
    row.action = action; row.expires_at = expiry; row.note = note.strip()[:300]; row.created_by = u.id
    db.commit(); audit(db, request, u, "lesson_access_override_updated", {"lesson_id": lesson.id, "student_id": student.id, "action": action})
    return RedirectResponse(f"/admin/lesson/{lesson.id}/edit#drip-control", 303)

@router.post("/admin/lesson/{lesson_id}/video-profile")
def update_lesson_video_profile(lesson_id: int, request: Request, provider: str = Form("external"), stream_type: str = Form("auto"), drm_mode: str = Form("none"), processing_status: str = Form("ready"), thumbnail_url: str = Form(""), duration_minutes: int = Form(0), duration_seconds: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    course = db.get(Course, lesson.course_id)
    if not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    provider = provider.strip().lower()[:40]
    stream_type = stream_type.strip().lower()[:20]
    drm_mode = drm_mode.strip().lower()[:30]
    processing_status = processing_status.strip().lower()[:20]
    if provider not in {"external","cloudflare","bunny","vimeo","mux","custom"}: raise HTTPException(400, "مزود الفيديو غير صالح")
    if stream_type not in {"auto","hls","dash","mp4"}: raise HTTPException(400, "نوع البث غير صالح")
    if drm_mode not in {"none","signed","widevine","fairplay","playready","multi-drm"}: raise HTTPException(400, "إعداد DRM غير صالح")
    if processing_status not in {"draft","uploading","processing","ready","blocked"}: raise HTTPException(400, "حالة الفيديو غير صالحة")
    if provider == "cloudflare":
        if not extract_stream_uid(lesson.video_url):
            raise HTTPException(400, "رابط الدرس يجب أن يكون رابط Cloudflare Stream صالحًا قبل اختيار المزود")
        drm_mode = "signed"
    clean_thumb = validated_video_url(thumbnail_url) if thumbnail_url.strip() else ""
    total_duration = max(0, min(int(duration_minutes), 9999) * 60 + min(max(int(duration_seconds), 0), 59))
    profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson.id).first()
    if not profile:
        profile = LessonVideoProfile(lesson_id=lesson.id)
        db.add(profile)
    profile.provider = provider; profile.stream_type = stream_type; profile.drm_mode = drm_mode
    profile.processing_status = processing_status; profile.thumbnail_url = clean_thumb; profile.duration_seconds = total_duration
    db.commit()
    audit(db, request, u, "lesson_video_profile_updated", {"lesson_id": lesson.id, "provider": provider, "stream_type": stream_type, "drm_mode": drm_mode, "status": processing_status})
    return RedirectResponse(f"/admin/lesson/{lesson.id}/edit#video-control", 303)

@router.post("/admin/lesson/{lesson_id}/move")
def move_lesson(lesson_id: int, request: Request, direction: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    course = db.get(Course, lesson.course_id)
    if not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    siblings = db.query(Lesson).filter(Lesson.course_id == course.id).order_by(Lesson.order_index, Lesson.id).all()
    try: idx = next(i for i, item in enumerate(siblings) if item.id == lesson.id)
    except StopIteration: raise HTTPException(404)
    target_idx = idx - 1 if direction == "up" else idx + 1 if direction == "down" else idx
    if 0 <= target_idx < len(siblings) and target_idx != idx:
        target = siblings[target_idx]
        lesson.order_index, target.order_index = target.order_index, lesson.order_index
        db.commit()
        audit(db, request, u, "lesson_reordered", {"lesson_id": lesson.id, "course_id": course.id, "direction": direction})
    return RedirectResponse(f"/admin/course/{course.id}#lesson-{lesson.id}", 303)

@router.post("/admin/lesson/{lesson_id}/toggle")
def toggle_lesson(lesson_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    c = db.get(Course, lesson.course_id)
    if not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    lesson.published = not lesson.published; db.commit(); audit(db, request, u, "lesson_publish_toggled", {"lesson_id": lesson.id, "published": lesson.published})
    return RedirectResponse(f"/admin/course/{c.id}", 303)

@router.post("/admin/lesson/{lesson_id}/delete")
def delete_lesson(lesson_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson: raise HTTPException(404)
    c = db.get(Course, lesson.course_id)
    if not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    if db.query(MediaAsset).filter(MediaAsset.lesson_id == lesson.id).count():
        raise HTTPException(409, "احذف الملفات المرتبطة بالدرس قبل حذف الدرس")
    db.query(LessonProgress).filter(LessonProgress.lesson_id == lesson.id).delete(synchronize_session=False)
    cp_ids = [x.id for x in db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id).all()]
    if cp_ids: db.query(CheckpointAttempt).filter(CheckpointAttempt.checkpoint_id.in_(cp_ids)).delete(synchronize_session=False)
    db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id).delete(synchronize_session=False)
    db.query(LessonFlashcard).filter_by(lesson_id=lesson.id).delete(synchronize_session=False)
    db.query(StudyAssistantLog).filter_by(lesson_id=lesson.id).delete(synchronize_session=False)
    db.query(OfflineGrant).filter_by(lesson_id=lesson.id).delete(synchronize_session=False)
    db.query(OfflineLessonPolicy).filter_by(lesson_id=lesson.id).delete(synchronize_session=False)
    db.delete(lesson); db.commit(); audit(db, request, u, "lesson_deleted", {"lesson_id": lesson_id, "course_id": c.id})
    return RedirectResponse(f"/admin/course/{c.id}", 303)

@router.post("/admin/course/{course_id}/lessons")
def add_lesson(course_id: int, request: Request, title: str = Form(...), body: str = Form(""), video_url: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c: raise HTTPException(404)
    if not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    order = db.query(Lesson).filter(Lesson.course_id == course_id).count() + 1
    clean_title = title.strip()[:180]
    if not clean_title: raise HTTPException(400, "عنوان الدرس مطلوب")
    lesson = Lesson(course_id=course_id, title=clean_title, body=body.strip(), video_url=validated_video_url(video_url), order_index=order, published=False)
    try:
        db.add(lesson)
        db.flush()
        audit(db, request, u, "add_lesson", {"lesson_id": lesson.id, "course_id": course_id}, commit=False)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logging.getLogger("lms").exception(
            "Lesson create failed course_id=%s request_id=%s",
            course_id, getattr(request.state, "request_id", ""),
        )
        raise HTTPException(
            500,
            "تعذر إنشاء الدرس داخل قاعدة البيانات. راجع Request ID في سجل الخادم.",
        )
    return RedirectResponse(f"/admin/lesson/{lesson.id}/edit?created=1#video-upload", 303)

@router.post("/admin/lesson/{lesson_id}/checkpoints")
def add_lesson_checkpoint(lesson_id: int, request: Request, timestamp_seconds: int = Form(0), question: str = Form(...), option_a: str = Form(...), option_b: str = Form(...), option_c: str = Form(...), option_d: str = Form(...), correct: str = Form(...), explanation: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not course or (not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id)): raise HTTPException(403)
    answer = correct.upper()[:1]
    if answer not in {"A", "B", "C", "D"}: raise HTTPException(400, "الإجابة الصحيحة يجب أن تكون A/B/C/D")
    cp = LessonCheckpoint(
        lesson_id=lesson.id, timestamp_seconds=max(0, min(int(timestamp_seconds), 43200)),
        question=question.strip()[:2000], option_a=option_a.strip()[:255], option_b=option_b.strip()[:255],
        option_c=option_c.strip()[:255], option_d=option_d.strip()[:255], correct=answer,
        explanation=explanation.strip()[:3000], published=True,
    )
    db.add(cp); db.commit(); audit(db, request, u, "lesson_checkpoint_created", {"lesson_id": lesson.id, "checkpoint_id": cp.id, "timestamp_seconds": cp.timestamp_seconds})
    return RedirectResponse(f"/admin/course/{course.id}#interactive-learning", 303)

@router.post("/admin/checkpoint/{checkpoint_id}/delete")
def delete_lesson_checkpoint(checkpoint_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    cp = db.get(LessonCheckpoint, checkpoint_id); lesson = db.get(Lesson, cp.lesson_id) if cp else None; course = db.get(Course, lesson.course_id) if lesson else None
    if not cp or not course or (not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id)): raise HTTPException(403)
    db.query(CheckpointAttempt).filter_by(checkpoint_id=cp.id).delete(synchronize_session=False)
    db.delete(cp); db.commit(); audit(db, request, u, "lesson_checkpoint_deleted", {"checkpoint_id": checkpoint_id})
    return RedirectResponse(f"/admin/course/{course.id}#interactive-learning", 303)

@router.post("/admin/lesson/{lesson_id}/flashcards")
def add_lesson_flashcard(lesson_id: int, request: Request, front: str = Form(...), back: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not course or (not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id)): raise HTTPException(403)
    order = db.query(LessonFlashcard).filter_by(lesson_id=lesson.id).count() + 1
    card = LessonFlashcard(lesson_id=lesson.id, front=front.strip()[:500], back=back.strip()[:3000], order_index=order, published=True)
    db.add(card); db.commit(); audit(db, request, u, "lesson_flashcard_created", {"lesson_id": lesson.id, "flashcard_id": card.id})
    return RedirectResponse(f"/admin/course/{course.id}#interactive-learning", 303)

@router.post("/admin/flashcard/{flashcard_id}/delete")
def delete_lesson_flashcard(flashcard_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    card = db.get(LessonFlashcard, flashcard_id); lesson = db.get(Lesson, card.lesson_id) if card else None; course = db.get(Course, lesson.course_id) if lesson else None
    if not card or not course or (not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id)): raise HTTPException(403)
    db.delete(card); db.commit(); audit(db, request, u, "lesson_flashcard_deleted", {"flashcard_id": flashcard_id})
    return RedirectResponse(f"/admin/course/{course.id}#interactive-learning", 303)

@router.post("/admin/lesson/{lesson_id}/offline-policy")
def set_offline_policy(lesson_id: int, request: Request, enabled: str = Form(""), provider_asset_id: str = Form(""), max_offline_days: int = Form(7), max_devices: int = Form(1), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not course or (not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id)): raise HTTPException(403)
    policy = db.query(OfflineLessonPolicy).filter_by(lesson_id=lesson.id).first()
    if not policy:
        policy = OfflineLessonPolicy(lesson_id=lesson.id); db.add(policy)
    policy.enabled = enabled.lower() in {"1", "true", "on", "yes"}
    policy.provider_asset_id = provider_asset_id.strip()[:255]
    policy.max_offline_days = max(1, min(int(max_offline_days), 30))
    policy.max_devices = max(1, min(int(max_devices), 3))
    db.commit(); audit(db, request, u, "offline_policy_updated", {"lesson_id": lesson.id, "enabled": policy.enabled})
    return RedirectResponse(f"/admin/course/{course.id}#offline-policy", 303)
