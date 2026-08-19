"""Student learning runtime routes extracted in V70.

This router owns the browser/mobile learning runtime HTTP contract while V70 keeps
selected helper implementations in app.main through a documented compatibility bridge.
The bridge is intentionally temporary; later releases can move those helpers into
domain services without changing public URLs.
"""
from datetime import datetime, timedelta
import json, os, random, secrets
import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import engine, get_db
from ..models import (
    CheckpointAttempt, ContentUnit, Course, DiscussionPost, Homework, HomeworkSubmission,
    Lesson, LessonCheckpoint, LessonProgress, MockExamAttemptAnalysis, MockExamProfile,
    Notification, OfflineGrant, OfflineLessonPolicy, Question, QuestionTaxonomy, Quiz,
    QuizAttempt, QuizQuestionSetting, StudyAssistantLog,
)
from ..request_context import DEVICE_COOKIE_NAME, audit, require_role, require_user, session_record, template_context as ctx
from ..security import check_csrf, device_fingerprint, sha256, verify_lesson_signature
from ..services.learning_runtime import (
    authorized_for_course, award_points, content_schedule_allows as _content_schedule_allows,
    course_completion_status as _course_completion_status, direct_video_proxy_enabled as _service_direct_video_proxy_enabled,
    issue_course_certificate as _issue_course_certificate, lesson_access_state as _lesson_access_state,
    lesson_unlocked as _lesson_unlocked, safe_range_header as _safe_range_header,
    validated_video_url as _service_validated_video_url,
)
from ..services.lesson_rendering import render_lesson_page as _render_lesson_page
from ..services.quiz_grading import grade_answers as _grade_answers, total_points as _quiz_total_points
from ..services.study_intelligence import smart_study_answer as _smart_study_answer
from ..services.template_rendering import render_template

def _is_production() -> bool:
    return os.getenv("ENV") == "production"

def _direct_video_proxy_enabled():
    return _service_direct_video_proxy_enabled(is_production=_is_production())

def validated_video_url(value: str) -> str:
    return _service_validated_video_url(value, is_production=_is_production())

_session_record = session_record

router = APIRouter()

def _pg_xact_lock(db, namespace: int, entity_id: int):
    """Serialize student mutations on PostgreSQL; SQLite tests are a no-op."""
    if engine.dialect.name == 'postgresql':
        safe_entity = int(entity_id) & 0x7FFFFFFF
        db.execute(text('SELECT pg_advisory_xact_lock(:ns, :entity)'), {'ns': int(namespace), 'entity': safe_entity})

@router.get("/homework/{homework_id}", response_class=HTMLResponse)
def homework_page(homework_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    h = db.get(Homework, homework_id)
    if not h or not h.published or not _content_schedule_allows(db, "homework", h.id) or not authorized_for_course(db, u, h.course_id): raise HTTPException(403)
    submission = db.query(HomeworkSubmission).filter_by(homework_id=h.id, student_id=u.id).first()
    return render_template("homework.html", ctx(request, db, homework=h, submission=submission))

@router.post("/homework/{homework_id}")
def submit_homework(homework_id: int, request: Request, answer_text: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    h = db.get(Homework, homework_id)
    if not h or not h.published or not _content_schedule_allows(db, "homework", h.id) or not authorized_for_course(db, u, h.course_id): raise HTTPException(403)
    _pg_xact_lock(db, 5506, (int(u.id) * 1000003 + int(h.id)))
    sub = db.query(HomeworkSubmission).filter_by(homework_id=h.id, student_id=u.id).first()
    if not sub: sub = HomeworkSubmission(homework_id=h.id, student_id=u.id); db.add(sub)
    first_submission = not bool(sub.answer_text)
    sub.answer_text = answer_text.strip(); sub.status = "submitted"; sub.submitted_at = datetime.utcnow()
    if first_submission: award_points(db, u.id, 10, "تسليم واجب", "homework", h.id)
    db.commit()
    audit(db, request, u, "homework_submitted", {"homework_id": h.id})
    return RedirectResponse(f"/homework/{h.id}", 303)

@router.get("/course/{course_id}", response_class=HTMLResponse)
def course_page(course_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    c = db.get(Course, course_id)
    if not c: raise HTTPException(404)
    if not authorized_for_course(db, u, course_id): raise HTTPException(403, "غير مشترك في الكورس")
    lessons = [x for x in db.query(Lesson).filter_by(course_id=course_id, published=True).order_by(Lesson.order_index).all() if _content_schedule_allows(db, "lesson", x.id)]
    quizzes = [x for x in db.query(Quiz).filter_by(course_id=course_id, published=True).all() if _content_schedule_allows(db, "quiz", x.id)]
    homeworks = [x for x in db.query(Homework).filter_by(course_id=course_id, published=True).order_by(Homework.id).all() if _content_schedule_allows(db, "homework", x.id)]
    progress_map = {p.lesson_id: p for p in db.query(LessonProgress).filter(LessonProgress.user_id == u.id, LessonProgress.lesson_id.in_([x.id for x in lessons] or [-1])).all()} if u.role == "student" else {}
    access_states = {lesson.id: _lesson_access_state(db, u, lesson) for lesson in lessons}
    unlocked = {lesson_id: state["unlocked"] for lesson_id, state in access_states.items()}
    completion = _course_completion_status(db, u.id, course_id) if u.role == "student" else None
    if completion and completion["complete"] and completion["policy"].certificate_enabled and not completion["certificate"]:
        completion["certificate"] = _issue_course_certificate(db, u.id, course_id)
    return render_template("course.html", ctx(request, db, course=c, lessons=lessons, quizzes=quizzes, homeworks=homeworks, progress_map=progress_map, unlocked=unlocked, access_states=access_states, completion=completion))

@router.get("/lesson/{lesson_id}", response_class=HTMLResponse)
def lesson_page(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not _content_schedule_allows(db, "lesson", lesson.id): raise HTTPException(404)
    if not authorized_for_course(db, u, lesson.course_id): raise HTTPException(403)
    if u.role == "student" and not _lesson_unlocked(db, u, lesson): raise HTTPException(403, "أكمل الدرس السابق أولًا")
    return _render_lesson_page(request, db, lesson, u)

@router.post("/lesson/{lesson_id}/assistant", response_class=HTMLResponse)
def lesson_assistant(lesson_id: int, request: Request, question: str = Form(...), mode: str = Form("explain"), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_user(request, db)
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not _content_schedule_allows(db, "lesson", lesson.id) or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(403)
    q = question.strip()[:1000]
    if len(q) < 2: raise HTTPException(400, "اكتب سؤالًا واضحًا")
    answer, source_kind = _smart_study_answer(db, lesson, q, u, mode)
    db.add(StudyAssistantLog(lesson_id=lesson.id, user_id=u.id, question=q, answer=answer, source_kind=source_kind))
    db.commit()
    audit(db, request, u, "study_assistant_question", {"lesson_id": lesson.id, "source_kind": source_kind})
    return _render_lesson_page(request, db, lesson, u, assistant_question=q, assistant_answer=answer)

@router.post("/lesson/{lesson_id}/checkpoint/{checkpoint_id}")
def answer_checkpoint(lesson_id: int, checkpoint_id: int, request: Request, answer: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id); cp = db.get(LessonCheckpoint, checkpoint_id)
    if not lesson or not _content_schedule_allows(db, "lesson", lesson.id) or not cp or cp.lesson_id != lesson.id or not cp.published or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(403)
    selected = (answer or "").strip().upper()
    if selected not in {"A", "B", "C", "D"}: raise HTTPException(400, "اختيار غير صالح")
    _pg_xact_lock(db, 5508, (int(u.id) * 1000003 + int(cp.id)))
    rec = db.query(CheckpointAttempt).filter_by(checkpoint_id=cp.id, student_id=u.id).first()
    first = rec is None
    if not rec:
        rec = CheckpointAttempt(checkpoint_id=cp.id, student_id=u.id); db.add(rec)
    rec.answer = selected; rec.is_correct = selected == cp.correct.upper(); rec.attempted_at = datetime.utcnow()
    if first:
        award_points(db, u.id, 5 if rec.is_correct else 2, "سؤال تفاعلي داخل الدرس", "checkpoint", cp.id)
    db.commit()
    audit(db, request, u, "lesson_checkpoint_answered", {"lesson_id": lesson.id, "checkpoint_id": cp.id, "correct": rec.is_correct})
    return RedirectResponse(f"/lesson/{lesson.id}?checkpoint={cp.id}#checkpoint-{cp.id}", 303)

@router.get("/api/mobile/offline/lesson/{lesson_id}/capability")
def offline_capability(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not _content_schedule_allows(db, "lesson", lesson.id) or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(403)
    policy = db.query(OfflineLessonPolicy).filter_by(lesson_id=lesson.id).first()
    provider_ready = bool((os.getenv("OFFLINE_DRM_LICENSE_URL") or os.getenv("DRM_LICENSE_SERVER_URL") or "").strip())
    return {
        "available": bool(policy and policy.enabled and provider_ready and policy.provider_asset_id),
        "inside_app_only": True,
        "provider_ready": provider_ready,
        "max_offline_days": policy.max_offline_days if policy else 0,
        "max_devices": policy.max_devices if policy else 0,
    }

@router.post("/api/mobile/offline/lesson/{lesson_id}/grant")
async def create_offline_grant(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    if "RagabSeddikMobile/" not in request.headers.get("user-agent", ""):
        raise HTTPException(403, "الحفظ الآمن بدون إنترنت متاح داخل التطبيق فقط")
    data = await request.json()
    if not check_csrf(request.session, data.get("csrf")): raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not _content_schedule_allows(db, "lesson", lesson.id) or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(403)
    policy = db.query(OfflineLessonPolicy).filter_by(lesson_id=lesson.id).first()
    license_url = (os.getenv("OFFLINE_DRM_LICENSE_URL") or os.getenv("DRM_LICENSE_SERVER_URL") or "").strip()
    if not policy or not policy.enabled or not policy.provider_asset_id or not license_url:
        raise HTTPException(503, "المشاهدة الآمنة بدون إنترنت تحتاج مزود DRM يدعم Offline licenses")
    fingerprint = device_fingerprint(
        request.headers.get("user-agent", ""), request.headers.get("accept-language", ""),
        request.cookies.get(DEVICE_COOKIE_NAME, ""),
    )
    active_count = db.query(OfflineGrant).filter(OfflineGrant.user_id == u.id, OfflineGrant.lesson_id == lesson.id, OfflineGrant.device_fingerprint != fingerprint, OfflineGrant.revoked_at.is_(None), OfflineGrant.expires_at > datetime.utcnow()).count()
    if active_count >= max(1, policy.max_devices): raise HTTPException(409, "تم الوصول للحد الأقصى للأجهزة للحفظ بدون إنترنت")
    raw = secrets.token_urlsafe(32)
    expiry = datetime.utcnow() + timedelta(days=max(1, min(policy.max_offline_days, 30)))
    db.add(OfflineGrant(user_id=u.id, lesson_id=lesson.id, token_hash=sha256(raw), device_fingerprint=fingerprint, expires_at=expiry))
    db.commit(); audit(db, request, u, "offline_grant_created", {"lesson_id": lesson.id, "expires_at": expiry.isoformat()})
    return {"grant": raw, "asset_id": policy.provider_asset_id, "license_url": license_url, "expires_at": expiry.isoformat() + "Z", "shareable": False, "inside_app_only": True}

@router.get("/protected/video/{lesson_id}")
def protected_video(lesson_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    """Session-bound proxy for direct MP4/WebM lesson URLs.

    This keeps the origin media URL out of the rendered lesson HTML and enforces
    the same enrollment/session checks on every browser request. It is an
    application security layer, not a replacement for provider DRM.
    """
    u = require_user(request, db)
    if not _direct_video_proxy_enabled():
        audit(db, request, u, "protected_video_denied", {"lesson_id": lesson_id, "reason": "direct_proxy_disabled"})
        raise HTTPException(404)
    rec = _session_record(request, db)
    if not rec or not verify_lesson_signature(token, lesson_id, u.id, rec.token_hash):
        audit(db, request, u, "protected_video_denied", {"lesson_id": lesson_id, "reason": "bad_token"})
        raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not _content_schedule_allows(db, "lesson", lesson.id):
        raise HTTPException(404)
    if not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)):
        audit(db, request, u, "protected_video_denied", {"lesson_id": lesson_id, "reason": "not_authorized"})
        raise HTTPException(403)
    source = validated_video_url(lesson.video_url)
    lower = source.lower().split("?", 1)[0]
    if not (lower.endswith(".mp4") or lower.endswith(".webm")):
        raise HTTPException(400, "هذا المسار مخصص للفيديو المباشر فقط")

    forward_headers = {}
    range_header = _safe_range_header(request.headers.get("range"))
    if range_header:
        forward_headers["Range"] = range_header[:200]
    client = httpx.Client(follow_redirects=True, timeout=httpx.Timeout(20.0, read=60.0))
    try:
        upstream_request = client.build_request("GET", source, headers=forward_headers)
        upstream = client.send(upstream_request, stream=True)
        if upstream.status_code not in (200, 206):
            upstream.close(); client.close()
            raise HTTPException(502, "تعذر تشغيل الفيديو من مزود المحتوى")
    except HTTPException:
        raise
    except Exception:
        client.close()
        raise HTTPException(502, "تعذر الاتصال بمزود الفيديو")

    headers = {
        "Cache-Control": "no-store, private",
        "X-Content-Type-Options": "nosniff",
        "Content-Disposition": "inline",
        "Accept-Ranges": upstream.headers.get("accept-ranges", "bytes"),
        "Cross-Origin-Resource-Policy": "same-origin",
        "Vary": "Cookie, Range",
    }
    for key in ("content-range", "content-length", "etag", "last-modified"):
        if upstream.headers.get(key):
            headers[key.title()] = upstream.headers[key]
    media_type = upstream.headers.get("content-type") or ("video/webm" if lower.endswith(".webm") else "video/mp4")

    def body_iter():
        try:
            for chunk in upstream.iter_bytes(chunk_size=256 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()
            client.close()

    audit(db, request, u, "protected_video_authorized", {"lesson_id": lesson.id, "range": bool(range_header)})
    return StreamingResponse(body_iter(), status_code=upstream.status_code, media_type=media_type, headers=headers)

@router.get("/protected/lesson/{lesson_id}")
def protected_lesson(lesson_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    rec = _session_record(request, db)
    if not rec or not verify_lesson_signature(token, lesson_id, u.id, rec.token_hash):
        audit(db, request, u, "protected_media_denied", {"lesson_id": lesson_id})
        raise HTTPException(403)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not _content_schedule_allows(db, "lesson", lesson.id) or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(404)
    audit(db, request, u, "protected_media_authorized", {"lesson_id": lesson_id})
    return JSONResponse({"lesson_id": lesson.id, "title": lesson.title, "status": "authorized", "ttl_seconds": 300})

@router.post("/api/lesson/{lesson_id}/progress")
async def lesson_progress(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not _content_schedule_allows(db, "lesson", lesson.id) or not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not _lesson_unlocked(db, u, lesson)): raise HTTPException(403)
    data = await request.json()
    if not check_csrf(request.session, data.get("csrf")): raise HTTPException(403)
    seconds = max(0, min(int(data.get("watched_seconds", 0)), 60 * 60 * 12))
    completed = bool(data.get("completed", False))
    _pg_xact_lock(db, 5505, (int(u.id) * 1000003 + int(lesson_id)))
    p = db.query(LessonProgress).filter_by(user_id=u.id, lesson_id=lesson_id).first()
    if not p:
        p = LessonProgress(user_id=u.id, lesson_id=lesson_id); db.add(p)
    p.watched_seconds = max(p.watched_seconds, seconds)
    was_completed = p.completed
    p.completed = p.completed or completed
    if p.completed and not was_completed:
        award_points(db, u.id, 20, "إكمال درس", "lesson", lesson_id)
        db.add(Notification(user_id=u.id, title="+20 نقطة", body=f"أكملت: {lesson.title}", kind="success"))
    db.commit()
    return {"ok": True, "watched_seconds": p.watched_seconds, "completed": p.completed}

@router.get("/quiz/{quiz_id}", response_class=HTMLResponse)
def quiz_page(quiz_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    qz = db.get(Quiz, quiz_id)
    if not qz or not qz.published or not _content_schedule_allows(db, "quiz", qz.id): raise HTTPException(404)
    if not authorized_for_course(db, u, qz.course_id): raise HTTPException(403)
    now = datetime.utcnow()
    session_key = f"quiz_attempt_{quiz_id}"
    attempt = None
    attempt_id = request.session.get(session_key)
    if attempt_id:
        attempt = db.get(QuizAttempt, int(attempt_id))
        if not attempt or attempt.user_id != u.id or attempt.quiz_id != quiz_id or attempt.status != "in_progress":
            request.session.pop(session_key, None); attempt = None
    if attempt and attempt.started_at + timedelta(minutes=qz.time_limit_minutes) <= now:
        attempt.status = "expired"; attempt.submitted_at = now; db.commit(); request.session.pop(session_key, None); attempt = None
    if not attempt:
        _pg_xact_lock(db, 5507, (int(u.id) * 1000003 + int(quiz_id)))
        # Reuse a still-live server-side attempt even if a concurrent browser request
        # has not yet received the signed session-cookie update.
        existing = db.query(QuizAttempt).filter(
            QuizAttempt.user_id == u.id, QuizAttempt.quiz_id == quiz_id, QuizAttempt.status == "in_progress"
        ).order_by(QuizAttempt.id.desc()).with_for_update().first()
        if existing and existing.started_at + timedelta(minutes=qz.time_limit_minutes) > now:
            attempt = existing
            request.session[session_key] = attempt.id
        else:
            if existing:
                existing.status = "expired"; existing.submitted_at = now
            used = db.query(QuizAttempt).filter(QuizAttempt.user_id == u.id, QuizAttempt.quiz_id == quiz_id).count()
            if used >= qz.max_attempts:
                db.commit()
                raise HTTPException(403, "تم استنفاد عدد المحاولات")
            qs_for_total = db.query(Question).filter_by(quiz_id=quiz_id).all()
            attempt = QuizAttempt(quiz_id=quiz_id, user_id=u.id, total=_quiz_total_points(db, qs_for_total), status="in_progress", started_at=now)
            db.add(attempt); db.commit(); request.session[session_key] = attempt.id
            audit(db, request, u, "quiz_started", {"quiz_id": quiz_id, "attempt_id": attempt.id})
    qs = db.query(Question).filter_by(quiz_id=quiz_id).all()
    if qz.shuffle_questions: random.Random(attempt.id).shuffle(qs)
    else:
        metas={m.question_id:m for m in db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id.in_([q.id for q in qs] or [-1])).all()}
        qs.sort(key=lambda q:(metas.get(q.id).position if metas.get(q.id) else q.id,q.id))
    deadline = attempt.started_at + timedelta(minutes=qz.time_limit_minutes)
    remaining_seconds = max(0, int((deadline - now).total_seconds()))
    return render_template("quiz.html", ctx(request, db, quiz=qz, questions=qs, attempt=attempt, remaining_seconds=remaining_seconds))

@router.post("/quiz/{quiz_id}", response_class=HTMLResponse)
async def submit_quiz(quiz_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "student")
    qz = db.get(Quiz, quiz_id)
    if not qz or not qz.published or not _content_schedule_allows(db, "quiz", qz.id) or not authorized_for_course(db, u, qz.course_id): raise HTTPException(403)
    form = await request.form()
    if not check_csrf(request.session, form.get("csrf")): raise HTTPException(403)
    session_key = f"quiz_attempt_{quiz_id}"
    attempt_id = request.session.get(session_key)
    _pg_xact_lock(db, 5507, (int(u.id) * 1000003 + int(quiz_id)))
    attempt = db.query(QuizAttempt).filter(QuizAttempt.id == int(attempt_id)).with_for_update().first() if attempt_id else None
    if not attempt or attempt.user_id != u.id or attempt.quiz_id != quiz_id or attempt.status != "in_progress": raise HTTPException(409, "لا توجد محاولة اختبار نشطة")
    now = datetime.utcnow()
    if attempt.started_at + timedelta(minutes=qz.time_limit_minutes) < now:
        attempt.status = "expired"; attempt.submitted_at = now; db.commit(); request.session.pop(session_key, None)
        raise HTTPException(408, "انتهى وقت الاختبار")
    qs = db.query(Question).filter_by(quiz_id=quiz_id).all()
    answers = {str(q.id): form.get(f"q_{q.id}", "") for q in qs}
    graded = _grade_answers(db, qs, answers)
    details = graded["details"]
    score = graded["score"]
    total = graded["total"]
    pct = graded["percentage"]
    attempt.score = score; attempt.total = total; attempt.status = "submitted"; attempt.submitted_at = now
    award_points(db, u.id, 15 if pct < 80 else 30, "إنهاء اختبار", "quiz_attempt", attempt.id)
    if pct >= 80: db.add(Notification(user_id=u.id, title="إنجاز جديد", body=f"حصلت على {pct:.0f}% في {qz.title} و+30 نقطة", kind="success"))
    mock_profile=db.query(MockExamProfile).filter_by(quiz_id=qz.id).first()
    mock_analysis=None
    if mock_profile:
        qtax={x.question_id:x for x in db.query(QuestionTaxonomy).filter(QuestionTaxonomy.question_id.in_([q.id for q in qs] or [-1])).all()}
        units={x.id:x for x in db.query(ContentUnit).filter(ContentUnit.id.in_([t.unit_id for t in qtax.values() if t.unit_id] or [-1])).all()}
        by_unit={}; by_diff={}
        for q,d in zip(qs,details):
            tax=qtax.get(q.id); diff=(tax.difficulty if tax else "غير مصنف"); uname=(units.get(tax.unit_id).name if tax and tax.unit_id in units else "عام")
            for bucket,key in ((by_unit,uname),(by_diff,diff)):
                row=bucket.setdefault(key,{"correct":0,"total":0}); row["total"]+=1; row["correct"]+=1 if d["is_correct"] else 0
        def rows(bucket):
            out=[]
            for name,row in bucket.items():
                acc=round(row["correct"]*100/row["total"]) if row["total"] else 0
                out.append({"name":name,"correct":row["correct"],"total":row["total"],"accuracy":acc,"level":"قوة" if acc>=80 else ("متوسط" if acc>=60 else "يحتاج مراجعة")})
            return sorted(out,key=lambda x:(x["accuracy"],x["name"]))
        mock_analysis={"by_unit":rows(by_unit),"by_difficulty":rows(by_diff),"overall":round(pct)}
        db.add(MockExamAttemptAnalysis(attempt_id=attempt.id,analysis_json=json.dumps(mock_analysis,ensure_ascii=False)))
    db.commit(); request.session.pop(session_key, None)
    audit(db, request, u, "quiz_attempt", {"quiz_id": quiz_id, "attempt_id": attempt.id, "score": score, "total": total, "percentage": round(pct, 1)})
    return render_template("quiz_result.html", ctx(request, db, score=score, total=total, details=details, quiz=qz, mock_analysis=mock_analysis, mock_profile=mock_profile))

@router.post("/lesson/{lesson_id}/discussion")
def discussion_add(lesson_id:int,request:Request,body:str=Form(...),parent_id:int|None=Form(None),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_user(request,db)
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    lesson=db.get(Lesson,lesson_id)
    if not lesson or not authorized_for_course(db,u,lesson.course_id): raise HTTPException(403)
    text=body.strip()
    if len(text)<2 or len(text)>2000: raise HTTPException(400,"طول المشاركة غير صالح")
    if parent_id:
        parent=db.get(DiscussionPost,parent_id)
        if not parent or parent.lesson_id!=lesson_id: raise HTTPException(400)
    db.add(DiscussionPost(lesson_id=lesson_id,user_id=u.id,parent_id=parent_id,body=text,status="visible")); db.commit()
    audit(db,request,u,"discussion_posted",{"lesson_id":lesson_id})
    return RedirectResponse(f"/lesson/{lesson_id}#discussion",303)