from __future__ import annotations

import logging
import os
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from ..access import authorized_for_course, content_schedule_allows, lesson_access_state
from ..cloudflare_stream import extract_stream_uid
from ..cloudflare_upload import (
    StreamUploadError, create_tus_upload, enforce_signed_video,
    max_upload_bytes as stream_max_upload_bytes, stream_video_details, valid_stream_uid,
)
from ..db import get_db
from ..models import Course, Lesson, LessonVideoProfile, MediaAsset
from ..permissions import can_manage_course
from ..request_context import audit, require_role, require_user
from ..security import check_csrf
from ..services.media import media_return_path, normalize_media_type, stream_state, valid_upload_signature, validate_upload_structure
from ..storage import read_private_bytes, save_upload_file
from ..watermark import trace_text, watermark_image, watermark_pdf

router = APIRouter(tags=["media"])
IS_PRODUCTION = os.getenv("ENV") == "production"


def _compat_callable(name: str, fallback):
    """Honor V57-V66 monkeypatch seams while routers are being extracted.

    The production callable remains the module implementation; tests and any
    internal extension that patched app.main keep working during migration.
    """
    try:
        from .. import main as legacy_main
        candidate = getattr(legacy_main, name, None)
        return candidate if callable(candidate) else fallback
    except Exception:
        return fallback


def _stream_upload_actor(lesson_id: int, request: Request, db: Session):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    token = request.headers.get("x-csrf-token", "")
    if not check_csrf(request.session, token):
        raise HTTPException(403, "رمز حماية الطلب غير صالح. حدّث الصفحة وحاول مرة أخرى.")
    lesson = db.get(Lesson, lesson_id)
    course = db.get(Course, lesson.course_id) if lesson else None
    if not lesson or not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id):
        raise HTTPException(403, "ليست لديك صلاحية رفع محاضرة لهذا الدرس.")
    return u, lesson, course


async def _request_json(request: Request) -> dict:
    try: payload = await request.json()
    except Exception: raise HTTPException(400, "بيانات طلب الرفع غير صالحة.")
    if not isinstance(payload, dict): raise HTTPException(400, "بيانات طلب الرفع غير صالحة.")
    return payload


def _stream_profile(db: Session, lesson_id: int) -> LessonVideoProfile:
    profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id).first()
    if not profile:
        profile = LessonVideoProfile(lesson_id=lesson_id); db.add(profile)
    return profile


@router.post("/admin/lesson/{lesson_id}/stream-upload/init")
async def init_stream_upload(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u, lesson, course = _stream_upload_actor(lesson_id, request, db)
    payload = await _request_json(request)
    file_name = os.path.basename(str(payload.get("file_name") or "")).strip()[:255]
    content_type = str(payload.get("content_type") or "application/octet-stream").strip().lower()[:120]
    try: file_size = int(payload.get("file_size"))
    except (TypeError, ValueError): raise HTTPException(400, "حجم ملف المحاضرة غير صالح.")
    extension = os.path.splitext(file_name)[1].lower()
    if not file_name or extension not in {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi", ".mpeg", ".mpg"}:
        raise HTTPException(415, "صيغة الفيديو غير مدعومة. استخدم MP4 أو MOV أو M4V أو MKV أو WebM.")
    if not (content_type.startswith("video/") or content_type in {"application/octet-stream", "application/x-matroska"}):
        raise HTTPException(415, "الملف المحدد ليس ملف فيديو صالحًا.")
    if file_size <= 0 or file_size > _compat_callable("stream_max_upload_bytes", stream_max_upload_bytes)(): raise HTTPException(413, "حجم المحاضرة خارج الحد المسموح لخدمة Stream.")
    try:
        item = _compat_callable("create_tus_upload", create_tus_upload)(file_name=file_name, file_size=file_size, content_type=content_type, creator=f"mostashar-u{u.id}-l{lesson.id}")
    except StreamUploadError as exc:
        raise HTTPException(exc.status_code, exc.public_message)
    profile = _stream_profile(db, lesson.id); profile.provider = "cloudflare"; profile.stream_type = "auto"; profile.drm_mode = "signed"; profile.processing_status = "uploading"
    db.commit(); audit(db, request, u, "stream_upload_initialized", {"lesson_id": lesson.id, "course_id": course.id, "uid": item["uid"], "file_name": file_name, "size_bytes": file_size})
    return JSONResponse(item)


@router.post("/admin/lesson/{lesson_id}/stream-upload/finalize")
async def finalize_stream_upload(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u, lesson, course = _stream_upload_actor(lesson_id, request, db); payload = await _request_json(request); uid = str(payload.get("uid") or "").strip()
    if not valid_stream_uid(uid): raise HTTPException(400, "معرّف الفيديو غير صالح.")
    try:
        result = _compat_callable("stream_video_details", stream_video_details)(uid)
        if str(result.get("creator") or "") != f"mostashar-u{u.id}-l{lesson.id}": raise HTTPException(403, "الفيديو لا يطابق عملية الرفع التي بدأها هذا الحساب لهذا الدرس.")
        _compat_callable("enforce_signed_video", enforce_signed_video)(uid)
    except StreamUploadError as exc:
        raise HTTPException(exc.status_code, exc.public_message)
    state, percent, error_code, error_text = stream_state(result)
    profile = _stream_profile(db, lesson.id); profile.provider = "cloudflare"; profile.stream_type = "auto"; profile.drm_mode = "signed"; profile.processing_status = "blocked" if state == "error" else ("ready" if state == "ready" and result.get("readyToStream") else "processing")
    try: profile.duration_seconds = max(0, int(round(float(result.get("duration") or 0))))
    except (TypeError, ValueError): profile.duration_seconds = 0
    thumbnail = str(result.get("thumbnail") or "")
    if thumbnail.startswith("https://"): profile.thumbnail_url = thumbnail[:500]
    lesson.video_url = f"https://videodelivery.net/{uid}/iframe"; lesson.published = False
    db.commit(); audit(db, request, u, "stream_upload_finalized", {"lesson_id": lesson.id, "course_id": course.id, "uid": uid, "state": state, "percent": percent, "error_code": error_code})
    if state == "error": message = "استلمت الخدمة الفيديو لكنه فشل في المعالجة." + ((" " + error_text) if error_text else "")
    elif profile.processing_status == "ready": message = "المحاضرة جاهزة. راجعها ثم فعّل نشر الدرس للطلاب."
    else: message = f"اكتمل الرفع وبدأت المعالجة ({percent:.0f}%). اترك الدرس مسودة حتى يصبح جاهزًا."
    return JSONResponse({"uid": uid, "state": state, "percent": percent, "message": message})


@router.post("/admin/lesson/{lesson_id}/stream-upload/status")
async def refresh_stream_upload_status(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    u, lesson, course = _stream_upload_actor(lesson_id, request, db); payload = await _request_json(request); uid = str(payload.get("uid") or "").strip(); current_uid = extract_stream_uid(lesson.video_url) or ""
    if not valid_stream_uid(uid) or uid != current_uid: raise HTTPException(400, "معرّف الفيديو لا يطابق المحاضرة الحالية.")
    try: result = _compat_callable("stream_video_details", stream_video_details)(uid)
    except StreamUploadError as exc: raise HTTPException(exc.status_code, exc.public_message)
    state, percent, error_code, error_text = stream_state(result)
    profile = _stream_profile(db, lesson.id); profile.provider = "cloudflare"; profile.drm_mode = "signed"; profile.processing_status = "blocked" if state == "error" else ("ready" if state == "ready" and result.get("readyToStream") else "processing")
    try: profile.duration_seconds = max(profile.duration_seconds, int(round(float(result.get("duration") or 0))))
    except (TypeError, ValueError): pass
    db.commit(); audit(db, request, u, "stream_upload_status_refreshed", {"lesson_id": lesson.id, "course_id": course.id, "uid": uid, "state": state, "percent": percent, "error_code": error_code})
    if state == "error": message = "فشلت معالجة الفيديو." + ((" " + error_text) if error_text else "")
    elif profile.processing_status == "ready": message = "أصبحت المحاضرة جاهزة. راجعها ثم انشر الدرس."
    else: message = f"المحاضرة ما زالت قيد المعالجة: {percent:.0f}%."
    return JSONResponse({"uid": uid, "state": state, "percent": percent, "message": message})


@router.post("/admin/course/{course_id}/media")
async def upload_course_media(course_id: int, request: Request, lesson_id: int = Form(...), csrf: str = Form(...), return_to: str = Form(""), file: UploadFile = File(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403, "رمز حماية الطلب غير صالح. حدّث الصفحة وحاول مرة أخرى.")
    c = db.get(Course, course_id); lesson = db.get(Lesson, lesson_id)
    if not c or not lesson or lesson.course_id != c.id or not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403, "ليست لديك صلاحية رفع ملف لهذا الدرس.")
    original_name = os.path.basename(file.filename or "").strip()[:255]; normalized_mime, expected_mime = normalize_media_type(original_name, file.content_type or "")
    if normalized_mime not in {"application/pdf", "video/mp4", "video/webm", "image/png", "image/jpeg"}: raise HTTPException(415, "نوع الملف غير مسموح. استخدم PDF أو PNG أو JPG، وارفع الفيديو من أداة Stream.")
    if expected_mime != normalized_mime: raise HTTPException(415, "امتداد الملف لا يطابق محتواه.")
    if IS_PRODUCTION and normalized_mime.startswith("video/"): raise HTTPException(409, "استخدم أداة رفع المحاضرة القابلة للاستكمال داخل صفحة تحرير الدرس.")
    await file.seek(0); head = await file.read(64)
    if not valid_upload_signature(head, normalized_mime): raise HTTPException(415, "الملف تالف أو توقيعه لا يطابق النوع المحدد.")
    await file.seek(0); file.file.seek(0, 2); size_bytes = file.file.tell(); file.file.seek(0)
    max_size = 60 * 1024 * 1024 if normalized_mime in {"application/pdf", "image/png", "image/jpeg"} else 250 * 1024 * 1024
    if size_bytes > max_size: raise HTTPException(413, "الملف أكبر من الحد المسموح لهذا النوع.")
    if size_bytes <= 0: raise HTTPException(400, "الملف فارغ.")
    try: validate_upload_structure(file.file, normalized_mime)
    except ValueError as exc:
        code = str(exc)
        if code == "image_too_large": raise HTTPException(413, "أبعاد الصورة أكبر من الحد الآمن للمعالجة")
        if code == "encrypted_pdf": raise HTTPException(415, "ملفات PDF المشفرة بكلمة مرور غير مدعومة")
        if code == "too_many_pages": raise HTTPException(413, "عدد صفحات PDF أكبر من الحد الآمن للمعالجة")
        if code == "invalid_image": raise HTTPException(415, "ملف الصورة تالف أو غير قابل للقراءة")
        raise HTTPException(415, "ملف PDF تالف أو غير قابل للقراءة")
    file.file.seek(0)
    try: key, provider = save_upload_file(file.file, original_name or "content.bin")
    except Exception:
        logging.getLogger("lms").exception("Private media upload failed for lesson %s", lesson.id); raise HTTPException(502, "تعذر حفظ الملف في التخزين. تأكد من صلاحيات القرص (Volume) في الخادم ثم أعد المحاولة.")
    asset = MediaAsset(lesson_id=lesson.id, owner_id=u.id, original_name=original_name or "content", storage_key=key, mime_type=normalized_mime, size_bytes=size_bytes, provider=provider)
    try: db.add(asset); db.commit()
    except Exception:
        db.rollback()
        try:
            from ..storage import delete_private
            delete_private(key, provider)
        except Exception: pass
        raise HTTPException(500, "تم رفع الملف لكن تعذر ربطه بالدرس. أعد المحاولة.")
    audit(db, request, u, "protected_media_uploaded", {"asset_id": asset.id, "lesson_id": lesson.id}); target = media_return_path(course_id, lesson.id, return_to)
    if request.headers.get("accept", "").startswith("application/json"): return JSONResponse({"message": "تم رفع الملف وربطه بالدرس بنجاح.", "asset_id": asset.id, "return_to": target})
    return RedirectResponse(target, 303)


@router.post("/admin/media/{asset_id}/delete")
def delete_media(asset_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    a = db.get(MediaAsset, asset_id)
    if not a or not a.lesson_id: raise HTTPException(404)
    lesson = db.get(Lesson, a.lesson_id); course = db.get(Course, lesson.course_id)
    if not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    try:
        if a.provider == "local":
            from ..storage import ROOT
            path = (ROOT / a.storage_key).resolve()
            if ROOT in path.parents and path.exists(): path.unlink()
        # Legacy rows with provider == "s3" from before R2 was removed: nothing
        # to clean up here (R2 credentials are gone), the DB row is still deleted below.
    except Exception: raise HTTPException(502, "تعذر حذف الملف من التخزين الخاص")
    db.delete(a); db.commit(); audit(db, request, u, "protected_media_deleted", {"asset_id": asset_id, "course_id": course.id})
    return RedirectResponse(f"/admin/course/{course.id}", 303)


@router.get("/protected/media/{asset_id}")
def protected_media(asset_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db); a = db.get(MediaAsset, asset_id)
    if not a or not a.lesson_id: raise HTTPException(404)
    lesson = db.get(Lesson, a.lesson_id)
    if not lesson or not lesson.published or not content_schedule_allows(db, "lesson", lesson.id): raise HTTPException(404)
    if not authorized_for_course(db, u, lesson.course_id) or (u.role == "student" and not bool(lesson_access_state(db, u, lesson)["unlocked"])):
        audit(db, request, u, "protected_asset_denied", {"asset_id": a.id, "lesson_id": lesson.id}); raise HTTPException(403)
    audit(db, request, u, "protected_asset_access", {"asset_id": a.id, "mime": a.mime_type})
    if a.mime_type.startswith("video/") and IS_PRODUCTION: raise HTTPException(503, "الفيديو الخام غير متاح في Production. استخدم مزود DRM/Streaming المعتمد.")
    wm = trace_text(u.id, u.email, u.name)
    try:
        if a.mime_type == "application/pdf":
            data = watermark_pdf(read_private_bytes(a.storage_key), wm); return Response(data, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=protected.pdf", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})
        if a.mime_type in {"image/png", "image/jpeg"}:
            fmt = "PNG" if a.mime_type == "image/png" else "JPEG"; data = watermark_image(read_private_bytes(a.storage_key), wm, fmt); return Response(data, media_type=a.mime_type, headers={"Content-Disposition": "inline", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})
    except ValueError: raise HTTPException(413, "الملف أكبر من حد المعالجة الديناميكية. استخدم نسخة مهيأة للمحتوى المحمي.")
    except FileNotFoundError: raise HTTPException(404)
    if a.provider not in ("local",):
        raise HTTPException(410, "هذا الملف مخزّن على مزود قديم (R2) لم يعد مدعومًا. أعد رفعه من جديد.")
    from ..storage import ROOT
    path = (ROOT / a.storage_key).resolve()
    if ROOT not in path.parents or not path.exists(): raise HTTPException(404)
    return FileResponse(path, media_type=a.mime_type, filename=None, headers={"Content-Disposition": "inline", "Cache-Control": "no-store, private"})