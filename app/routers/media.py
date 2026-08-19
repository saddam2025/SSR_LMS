from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..access import authorized_for_course, content_schedule_allows, lesson_access_state
from ..cloudflare_stream import extract_stream_uid
from ..cloudflare_upload import (
    StreamUploadError, create_tus_upload, enforce_signed_video,
    max_upload_bytes as stream_max_upload_bytes, stream_video_details, valid_stream_uid,
)
from ..db import engine, get_db
from ..models import Course, Lesson, LessonVideoProfile, MediaAsset
from ..permissions import can_manage_course
from ..request_context import audit, require_role, require_user
from ..security import check_csrf
from ..services.media import media_return_path, normalize_media_type, stream_state, valid_upload_signature, validate_upload_structure
from ..storage import (
    delete_private, download_private_to_file, head_private, new_storage_key,
    presigned_get, presigned_put, read_private_bytes, read_private_range,
    s3_ready, save_upload_file,
)
from ..watermark import WatermarkCapacityExceeded, trace_text, watermark_capacity, watermark_image, watermark_pdf

router = APIRouter(tags=["media"])
IS_PRODUCTION = os.getenv("ENV") == "production"
DIRECT_R2_UPLOAD_ENABLED = os.getenv("DIRECT_R2_UPLOAD_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
DIRECT_R2_UPLOAD_TTL_SECONDS = max(120, min(int(os.getenv("DIRECT_R2_UPLOAD_TTL_SECONDS", "1200")), 3600))
DOCUMENT_MIMES = {"application/pdf", "image/png", "image/jpeg"}


def _pg_xact_lock(db: Session, namespace: int, entity_id: int) -> None:
    """Serialize a production mutation across Railway workers on PostgreSQL."""
    if engine.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:ns, :entity)"),
            {"ns": int(namespace), "entity": int(entity_id) & 0x7FFFFFFF},
        )


def _storage_lock_id(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8", "ignore")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _direct_upload_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.getenv("APP_SECRET", "dev-secret-change-this-immediately"), salt="mostashar-r2-upload-v1")


def _media_actor(course_id: int, lesson_id: int, request: Request, db: Session):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    c = db.get(Course, course_id); lesson = db.get(Lesson, lesson_id)
    if not c or not lesson or lesson.course_id != c.id or not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id):
        raise HTTPException(403, "ليست لديك صلاحية رفع ملف لهذا الدرس.")
    return u, c, lesson


def _media_policy(file_name: str, declared_mime: str, file_size: int):
    original_name = os.path.basename(file_name or "").strip()[:255]
    normalized_mime, expected_mime = normalize_media_type(original_name, declared_mime or "")
    if normalized_mime not in DOCUMENT_MIMES:
        raise HTTPException(415, "نوع الملف غير مسموح. استخدم PDF أو PNG أو JPG، وارفع الفيديو من أداة Stream.")
    if expected_mime != normalized_mime:
        raise HTTPException(415, "امتداد الملف لا يطابق محتواه.")
    max_size = 60 * 1024 * 1024
    if file_size <= 0:
        raise HTTPException(400, "الملف فارغ.")
    if file_size > max_size:
        raise HTTPException(413, "الملف أكبر من الحد المسموح لهذا النوع.")
    return original_name or "content", normalized_mime, max_size


def _validate_remote_upload(key: str, normalized_mime: str, expected_size: int) -> None:
    info = head_private(key)
    actual_size = int(info.get("ContentLength") or 0)
    if actual_size != expected_size:
        raise ValueError("size_mismatch")
    head = read_private_range(key, 0, 63)
    if not valid_upload_signature(head, normalized_mime):
        raise ValueError("signature_mismatch")
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as tmp:
        download_private_to_file(key, tmp)
        validate_upload_structure(tmp, normalized_mime)


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


def _stream_profile(db: Session, lesson_id: int, *, lock: bool = False) -> LessonVideoProfile:
    query = db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id)
    if lock and engine.dialect.name == "postgresql":
        query = query.with_for_update()
    profile = query.first()
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
    # One active Stream upload per lesson: prevents double-click/retry races across web workers.
    _pg_xact_lock(db, 5531, lesson.id)
    current_profile = _stream_profile(db, lesson.id, lock=True)
    active_since = current_profile.updated_at
    if current_profile.processing_status in {"uploading", "processing"} and active_since and active_since >= datetime.utcnow() - timedelta(minutes=30):
        raise HTTPException(409, "توجد عملية رفع أو معالجة فيديو جارية لهذا الدرس. استكمل الرفع الحالي أو انتظر قبل بدء عملية جديدة.")
    try:
        item = _compat_callable("create_tus_upload", create_tus_upload)(file_name=file_name, file_size=file_size, content_type=content_type, creator=f"mostashar-u{u.id}-l{lesson.id}")
    except StreamUploadError as exc:
        raise HTTPException(exc.status_code, exc.public_message)
    profile = current_profile; profile.provider = "cloudflare"; profile.stream_type = "auto"; profile.drm_mode = "signed"; profile.processing_status = "uploading"
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
    _pg_xact_lock(db, 5531, lesson.id)
    profile = _stream_profile(db, lesson.id, lock=True); profile.provider = "cloudflare"; profile.stream_type = "auto"; profile.drm_mode = "signed"; profile.processing_status = "blocked" if state == "error" else ("ready" if state == "ready" and result.get("readyToStream") else "processing")
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
    _pg_xact_lock(db, 5531, lesson.id)
    profile = _stream_profile(db, lesson.id, lock=True); profile.provider = "cloudflare"; profile.drm_mode = "signed"; profile.processing_status = "blocked" if state == "error" else ("ready" if state == "ready" and result.get("readyToStream") else "processing")
    try: profile.duration_seconds = max(profile.duration_seconds, int(round(float(result.get("duration") or 0))))
    except (TypeError, ValueError): pass
    db.commit(); audit(db, request, u, "stream_upload_status_refreshed", {"lesson_id": lesson.id, "course_id": course.id, "uid": uid, "state": state, "percent": percent, "error_code": error_code})
    if state == "error": message = "فشلت معالجة الفيديو." + ((" " + error_text) if error_text else "")
    elif profile.processing_status == "ready": message = "أصبحت المحاضرة جاهزة. راجعها ثم انشر الدرس."
    else: message = f"المحاضرة ما زالت قيد المعالجة: {percent:.0f}%."
    return JSONResponse({"uid": uid, "state": state, "percent": percent, "message": message})


@router.post("/admin/course/{course_id}/media-upload/init")
async def init_direct_media_upload(course_id: int, request: Request, db: Session = Depends(get_db)):
    if not (DIRECT_R2_UPLOAD_ENABLED and s3_ready()):
        raise HTTPException(409, "الرفع المباشر إلى R2 غير مفعّل؛ سيتم استخدام مسار الرفع الاحتياطي.")
    token = request.headers.get("x-csrf-token", "")
    if not check_csrf(request.session, token):
        raise HTTPException(403, "رمز حماية الطلب غير صالح. حدّث الصفحة وحاول مرة أخرى.")
    payload = await _request_json(request)
    try:
        lesson_id = int(payload.get("lesson_id"))
        file_size = int(payload.get("file_size"))
    except (TypeError, ValueError):
        raise HTTPException(400, "بيانات الملف غير صالحة.")
    u, c, lesson = _media_actor(course_id, lesson_id, request, db)
    original_name, normalized_mime, _ = _media_policy(str(payload.get("file_name") or ""), str(payload.get("content_type") or ""), file_size)
    key = new_storage_key(original_name, "protected")
    try:
        upload_url = await run_in_threadpool(presigned_put, key, normalized_mime, DIRECT_R2_UPLOAD_TTL_SECONDS)
    except Exception:
        logging.getLogger("lms").exception("Could not create direct R2 upload URL")
        raise HTTPException(502, "تعذر تجهيز رابط رفع R2. سيتم استخدام مسار الرفع الاحتياطي.")
    signed = _direct_upload_serializer().dumps({
        "u": u.id, "c": c.id, "l": lesson.id, "k": key, "n": original_name,
        "m": normalized_mime, "s": file_size,
    })
    return JSONResponse({
        "upload_url": upload_url, "upload_token": signed, "content_type": normalized_mime,
        "expires_in": DIRECT_R2_UPLOAD_TTL_SECONDS,
    })


@router.post("/admin/course/{course_id}/media-upload/finalize")
async def finalize_direct_media_upload(course_id: int, request: Request, db: Session = Depends(get_db)):
    csrf = request.headers.get("x-csrf-token", "")
    if not check_csrf(request.session, csrf):
        raise HTTPException(403, "رمز حماية الطلب غير صالح. حدّث الصفحة وحاول مرة أخرى.")
    payload = await _request_json(request)
    signed = str(payload.get("upload_token") or "")
    try:
        item = _direct_upload_serializer().loads(signed, max_age=DIRECT_R2_UPLOAD_TTL_SECONDS)
    except SignatureExpired:
        raise HTTPException(409, "انتهت صلاحية عملية الرفع. أعد المحاولة.")
    except BadSignature:
        raise HTTPException(403, "بيانات عملية الرفع غير صالحة.")
    if not isinstance(item, dict):
        raise HTTPException(400, "بيانات عملية الرفع غير صالحة.")
    try:
        lesson_id = int(item["l"]); owner_id = int(item["u"]); expected_size = int(item["s"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(400, "بيانات عملية الرفع غير مكتملة.")
    u, c, lesson = _media_actor(course_id, lesson_id, request, db)
    if owner_id != u.id or int(item.get("c") or 0) != c.id:
        raise HTTPException(403, "عملية الرفع لا تخص هذا الحساب أو الكورس.")
    key = str(item.get("k") or "")
    normalized_mime = str(item.get("m") or "")
    original_name = str(item.get("n") or "content")[:255]
    if not key.startswith("protected/") or normalized_mime not in DOCUMENT_MIMES:
        raise HTTPException(400, "بيانات الملف المرفوع غير صالحة.")
    try:
        await run_in_threadpool(_validate_remote_upload, key, normalized_mime, expected_size)
    except ValueError as exc:
        try:
            await run_in_threadpool(delete_private, key, "s3")
        except Exception:
            pass
        code = str(exc)
        if code in {"image_too_large", "too_many_pages", "size_mismatch"}:
            raise HTTPException(413, "الملف المرفوع يتجاوز حدود المعالجة الآمنة.")
        if code == "encrypted_pdf":
            raise HTTPException(415, "ملفات PDF المشفرة بكلمة مرور غير مدعومة.")
        raise HTTPException(415, "الملف المرفوع تالف أو لا يطابق النوع المحدد.")
    except Exception:
        logging.getLogger("lms").exception("Direct R2 upload validation failed for lesson %s", lesson.id)
        raise HTTPException(502, "تعذر التحقق من الملف في R2. أعد المحاولة.")
    # Finalize is idempotent. A retried browser request must never delete an object
    # that another worker has already linked successfully.
    _pg_xact_lock(db, 5530, _storage_lock_id(key))
    existing = db.query(MediaAsset).filter_by(storage_key=key).with_for_update().first()
    if existing:
        if existing.lesson_id == lesson.id and existing.owner_id == u.id and existing.mime_type == normalized_mime and int(existing.size_bytes or 0) == expected_size:
            return JSONResponse({"message": "الملف مرتبط بالدرس بالفعل.", "asset_id": existing.id, "idempotent": True})
        raise HTTPException(409, "مفتاح التخزين مرتبط بملف آخر بالفعل.")
    asset = MediaAsset(
        lesson_id=lesson.id, owner_id=u.id, original_name=original_name, storage_key=key,
        mime_type=normalized_mime, size_bytes=expected_size, provider="s3",
    )
    try:
        db.add(asset); db.commit()
    except Exception:
        db.rollback()
        # A database uniqueness race may still happen on non-PostgreSQL test backends.
        # Re-read before cleanup so a successful concurrent finalizer never loses its object.
        existing = db.query(MediaAsset).filter_by(storage_key=key).first()
        if existing and existing.lesson_id == lesson.id and existing.owner_id == u.id:
            return JSONResponse({"message": "الملف مرتبط بالدرس بالفعل.", "asset_id": existing.id, "idempotent": True})
        try:
            await run_in_threadpool(delete_private, key, "s3")
        except Exception:
            pass
        raise HTTPException(500, "تم رفع الملف لكن تعذر ربطه بالدرس. أعد المحاولة.")
    audit(db, request, u, "protected_media_direct_uploaded", {"asset_id": asset.id, "lesson_id": lesson.id})
    return JSONResponse({"message": "تم رفع الملف مباشرة إلى التخزين وربطه بالدرس بنجاح.", "asset_id": asset.id, "idempotent": False})


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
    try: await run_in_threadpool(validate_upload_structure, file.file, normalized_mime)
    except ValueError as exc:
        code = str(exc)
        if code == "image_too_large": raise HTTPException(413, "أبعاد الصورة أكبر من الحد الآمن للمعالجة")
        if code == "encrypted_pdf": raise HTTPException(415, "ملفات PDF المشفرة بكلمة مرور غير مدعومة")
        if code == "too_many_pages": raise HTTPException(413, "عدد صفحات PDF أكبر من الحد الآمن للمعالجة")
        if code == "invalid_image": raise HTTPException(415, "ملف الصورة تالف أو غير قابل للقراءة")
        raise HTTPException(415, "ملف PDF تالف أو غير قابل للقراءة")
    file.file.seek(0)
    try: key, provider = await run_in_threadpool(save_upload_file, file.file, original_name or "content.bin")
    except Exception:
        logging.getLogger("lms").exception("Private media upload failed for lesson %s", lesson.id); raise HTTPException(502, "تعذر حفظ الملف في R2. راجع إعدادات Bucket والمفاتيح ثم أعد المحاولة.")
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
        elif a.provider == "s3":
            import boto3
            c = boto3.client("s3", endpoint_url=os.getenv("S3_ENDPOINT_URL") or None, region_name=os.getenv("S3_REGION") or None, aws_access_key_id=os.getenv("S3_ACCESS_KEY_ID"), aws_secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY")); c.delete_object(Bucket=os.environ["S3_BUCKET"], Key=a.storage_key)
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
            with watermark_capacity():
                data = watermark_pdf(read_private_bytes(a.storage_key), wm)
            return Response(data, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=protected.pdf", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})
        if a.mime_type in {"image/png", "image/jpeg"}:
            fmt = "PNG" if a.mime_type == "image/png" else "JPEG"
            with watermark_capacity():
                data = watermark_image(read_private_bytes(a.storage_key), wm, fmt)
            return Response(data, media_type=a.mime_type, headers={"Content-Disposition": "inline", "Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})
    except WatermarkCapacityExceeded:
        raise HTTPException(503, "خدمة حماية الملفات مشغولة مؤقتًا. حاول مرة أخرى بعد لحظات.", headers={"Retry-After": "3"})
    except ValueError: raise HTTPException(413, "الملف أكبر من حد المعالجة الديناميكية. استخدم نسخة مهيأة للمحتوى المحمي.")
    except FileNotFoundError: raise HTTPException(404)
    if a.provider == "s3": return RedirectResponse(presigned_get(a.storage_key, 120), 302)
    from ..storage import ROOT
    path = (ROOT / a.storage_key).resolve()
    if ROOT not in path.parents or not path.exists(): raise HTTPException(404)
    return FileResponse(path, media_type=a.mime_type, filename=None, headers={"Content-Disposition": "inline", "Cache-Control": "no-store, private"})
