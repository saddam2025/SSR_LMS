import os, json, random, re, secrets, io, zipfile, html, csv, base64
from contextlib import asynccontextmanager
import httpx
from urllib.parse import urlparse
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, text
from .db import Base, engine, get_db, ensure_schema
from .models import (
    User, Course, Lesson, Enrollment, Quiz, Question, QuizAttempt, AuditLog,
    Device, ActiveSession, LessonProgress, Subscription, Coupon, CouponRedemption,
    PaymentTransaction, Notification, MediaAsset, ParentStudent, Homework, HomeworkSubmission,
    StudentProfile, OTPChallenge, PointLedger, DiscussionPost, ActivationCode, ActivationRedemption, ActivationCodeBatch, ActivationCodeInventory, VocabularyItem, VocabularyReview, StudentStreak,
    LessonCheckpoint, CheckpointAttempt, LessonFlashcard, StudyAssistantLog, OfflineLessonPolicy, OfflineGrant, CourseCategory, CourseCategoryAssignment, SupportTicket, SupportTicketMessage, LessonVideoProfile, QuestionBankItem, QuizQuestionSetting, CommunicationCampaign, CommunicationDelivery, StudentAttendance, LiveClass, LiveClassAttendance, StudentGroup, StudentGroupMembership, GroupCourseAssignment, GroupLiveClassAssignment, ContentUnit, LessonUnitAssignment, QuizUnitAssignment, HomeworkUnitAssignment, CourseAcademicPeriod, ContentSchedule, LessonDripRule, LessonAccessOverride, CourseCompletionPolicy, CourseCertificate, RevisionPlan, RevisionTask, RevisionTaskProgress, QuestionBankTaxonomy, QuestionTaxonomy, MockExamProfile, MockExamAttemptAnalysis, StudentRemediationPlan, StudentRemediationItem, PushDevice, HomepageFeature, HomepageReel, HomepageHonor, HomepageReview
)
from .payment import create_intention, configured as paymob_configured, merchant_reference, verify_transaction_hmac
from .storage import save_upload_file, presigned_get, read_private_bytes
from .cloudflare_stream import extract_stream_uid, stream_edge_ready, stream_embed_path
from .cloudflare_upload import (
    StreamUploadError, create_tus_upload, enforce_signed_video,
    max_upload_bytes as stream_max_upload_bytes, stream_upload_ready,
    stream_video_details, valid_stream_uid,
)
from .watermark import watermark_pdf, watermark_image, trace_text
from .api_v1 import router as api_v1_router
from .routers.pwa import router as pwa_router
from .routers.system import router as system_router
from .routers.support import router as support_router
from .routers.media import router as media_router
from .routers.commerce import router as commerce_router
from .routers.auth import router as auth_router
from .routers.courses import router as courses_router
from .routers.communications import router as communications_router
from .routers.reports import router as reports_router
from .routers.admin_users import router as admin_users_router
from .routers.admin_security import router as admin_security_router
from .routers.parents import router as parents_router
from .routers.community import router as community_router
from .routers.homepage import router as homepage_router
from .routers.academic_content import router as academic_content_router
from .routers.remediation import router as remediation_router
from .routers.assessments_admin import router as assessments_admin_router
from .routers.push_notifications import router as push_notifications_router
from .routers.activation_codes import router as activation_codes_router
from .routers.dashboards import router as dashboards_router
from .routers.course_categories import router as course_categories_router
from .routers.student_experience import router as student_experience_router
from .routers.system_admin import router as system_admin_router
from .routers.certificates import router as certificates_router
from .routers.english_tools import router as english_tools_router
from .routers.discussion_admin import router as discussion_admin_router
from .services.reports import student_performance_rows as service_student_performance_rows
from .observability import configure_logging, metrics_middleware
from .production import production_status, enforce_production_core
from .security import (
    verify_password, ensure_csrf, check_csrf, login_allowed, record_failed_login,
    clear_failed_logins, sign_lesson, verify_lesson_signature, create_session_token,
    sha256, device_fingerprint, session_absolute_expiry, session_idle_deadline,
    MAX_DEVICES, REQUIRE_STAFF_MFA, STUDENT_SINGLE_SESSION, password_needs_rehash, hash_password,
    new_totp_secret, verify_totp, totp_uri, encrypt_secret, decrypt_secret
)
from . import push
from .permissions import STAFF_ROLES, ADMIN_ROLES, CONTENT_ROLES, COMMERCE_ROLES, SUPPORT_ROLES, SECURITY_ROLES, USER_ADMIN_ROLES, ALLOWED_ROLES, ROLE_LABELS, can_manage_course
from .access import authorized_for_course as access_authorized_for_course, content_schedule_allows as access_content_schedule_allows, lesson_access_state as access_lesson_access_state
from .services.auth import normalize_phone
from .services.courses import validated_video_url as course_validated_video_url
from .services.learning_runtime import (
    award_points as runtime_award_points, course_completion_status as runtime_course_completion_status,
    issue_course_certificate as runtime_issue_course_certificate,
    direct_video_proxy_enabled as runtime_direct_video_proxy_enabled, safe_range_header as runtime_safe_range_header,
    validated_video_url as runtime_validated_video_url,
)
from .services.study_intelligence import (
    study_tokens as service_study_tokens, student_learning_intelligence as service_student_learning_intelligence,
    smart_study_answer as service_smart_study_answer,
)
from .services.lesson_rendering import render_lesson_page as service_render_lesson_page
from .services.student_activity import student_last_activity as service_student_last_activity, student_last_activity_map as service_student_last_activity_map, student_weekly_attendance as service_student_weekly_attendance
from .services.community import student_live_classes as service_student_live_classes
from .services.academic_content import schedule_status as service_schedule_status

configure_logging()
enforce_production_core()
# Production schema preparation is performed once in Railway pre-deploy. Avoid
# import-time DB DDL/network I/O in each Uvicorn worker. Local/test keeps create_all.
if os.getenv("ENV", "development").lower() != "production":
    ensure_schema()

# One lightweight Redis-stream consumer per web process handles durable external
# communication tasks. Redis consumer-group semantics prevent duplicate workers
# from processing the same queued item, and stale jobs are reclaimed after crashes.
from .worker import start_background_worker, stop_background_worker

@asynccontextmanager
async def _app_lifespan(_app):
    start_background_worker()
    try:
        yield
    finally:
        stop_background_worker()

app = FastAPI(title="Ragab Seddik LMS", docs_url=None, redoc_url=None, lifespan=_app_lifespan)
app.add_middleware(GZipMiddleware, minimum_size=700)
app.middleware("http")(metrics_middleware)
IS_PRODUCTION = os.getenv("ENV") == "production"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
DEVICE_COOKIE_NAME = "__Host-lms_device" if IS_PRODUCTION else "lms_device"
if IS_PRODUCTION and (not PUBLIC_BASE_URL or not PUBLIC_BASE_URL.startswith("https://")):
    raise RuntimeError("PUBLIC_BASE_URL must be an HTTPS origin in production")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("APP_SECRET", "dev-secret-change-this-immediately"),
    session_cookie="__Host-lms_session" if IS_PRODUCTION else "lms_session",
    https_only=IS_PRODUCTION,
    same_site="lax",
    max_age=int(os.getenv("SESSION_ABSOLUTE_HOURS", "24")) * 3600,
)
if IS_PRODUCTION:
    base_host = urlparse(PUBLIC_BASE_URL).hostname or ""
    extra_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
    # Railway performs deployment healthchecks with this Host header. Keep it
    # explicitly trusted so /ready cannot be rejected before traffic is promoted.
    railway_health_host = "healthcheck.railway.app"
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(dict.fromkeys([base_host, railway_health_host, *extra_hosts])))

# V59 separated frontend: allow only explicitly configured frontend origins.
# Cookies remain HttpOnly and the API still performs server-side authorization.
FRONTEND_ORIGINS = [x.strip().rstrip("/") for x in os.getenv("FRONTEND_ORIGINS", "").split(",") if x.strip()]
if FRONTEND_ORIGINS:
    for origin in FRONTEND_ORIGINS:
        parsed = urlparse(origin)
        if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.path not in {"", "/"}:
            raise RuntimeError(f"Invalid FRONTEND_ORIGINS entry: {origin}")
        if IS_PRODUCTION and parsed.scheme != "https":
            raise RuntimeError("FRONTEND_ORIGINS must use HTTPS in production")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "X-CSRF-Token", "X-Requested-With"],
        expose_headers=["X-Request-ID"],
    )
APP_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")), name="static")
from .services.template_rendering import templates, render_template

@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    path = request.url.path
    if path.startswith("/api/"):
        # APIs preserve standards-correct 401/403 responses for mobile/desktop clients.
        return JSONResponse({"error":{"status":exc.status_code,"message":str(exc.detail),"request_id":getattr(request.state,"request_id",request.headers.get("x-request-id",""))}}, status_code=exc.status_code)
    wants_json = request.headers.get("accept", "").startswith("application/json")
    if wants_json:
        return JSONResponse({"detail":exc.detail}, status_code=exc.status_code)
    if exc.status_code == 401:
        # Browser sessions should recover cleanly instead of exposing a raw 401 page.
        return RedirectResponse("/login?expired=1", status_code=303)
    if exc.status_code == 428:
        # Staff accounts must finish MFA setup before privileged menu pages are available.
        return RedirectResponse("/account/security?required=1", status_code=303)
    if exc.status_code == 403 and exc.detail == "role_forbidden" and request.method in {"GET", "HEAD"} and path != "/dashboard":
        # Do not weaken authorization: send an authenticated browser back to its role-aware dashboard.
        if request.session.get("sid"):
            return RedirectResponse("/dashboard?denied=1", status_code=303)
        return RedirectResponse("/login?expired=1", status_code=303)
    friendly = {
        400: "تعذر تنفيذ الطلب. راجع البيانات وحاول مرة أخرى.",
        403: "ليس لديك صلاحية لتنفيذ هذه العملية.",
        404: "الصفحة أو العنصر المطلوب غير موجود.",
        409: "تعذر تنفيذ العملية بسبب تعارض في البيانات.",
        413: "حجم الملف أكبر من الحد المسموح.",
        429: "عدد المحاولات كبير. حاول مرة أخرى بعد قليل.",
        502: "تعذر الاتصال بخدمة خارجية مطلوبة. راجع إعدادات التخزين أو الفيديو.",
        503: str(exc.detail) if isinstance(exc.detail, str) else "الخدمة غير مهيأة أو غير متاحة مؤقتًا.",
    }.get(exc.status_code, "تعذر إكمال الطلب. حاول مرة أخرى.")
    return HTMLResponse(
        f"<!doctype html><html lang='ar' dir='rtl'><meta charset='utf-8'><title>المستشار</title>"
        f"<body style='font-family:Arial,sans-serif;max-width:640px;margin:12vh auto;padding:24px;text-align:center'>"
        f"<h1>المستشار</h1><p>{friendly}</p><p><a href='/dashboard'>العودة إلى لوحتي</a> · <a href='/'>الرئيسية</a></p></body></html>",
        status_code=exc.status_code,
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    import logging
    logging.getLogger("lms").exception("Unhandled error on %s", request.url.path)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error":{"status":500,"message":"Internal server error"}}, status_code=500)
    request_id = getattr(request.state, "request_id", request.headers.get("x-request-id", ""))
    return HTMLResponse(
        "<h1>حدث خطأ مؤقت</h1><p>يرجى إعادة المحاولة بعد قليل.</p>"
        + (f"<p style='direction:ltr'>Request ID: {request_id}</p>" if request_id else ""),
        status_code=500,
    )

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "0"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=(), display-capture=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    video_hosts = [h.strip().lower() for h in os.getenv("VIDEO_ALLOWED_HOSTS", "").split(",") if h.strip()]
    frame_sources = " ".join(["'self'", *[f"https://{h}" for h in video_hosts], *[f"https://*.{h}" for h in video_hosts]]) if video_hosts else ("'self'" if IS_PRODUCTION else "'self' https:")
    resource_sources = " ".join(["'self'", *[f"https://{h}" for h in video_hosts], *[f"https://*.{h}" for h in video_hosts]]) if video_hosts else "'self'"
    connect_sources = ["'self'", "https://upload.videodelivery.net", "https://*.upload.videodelivery.net"]
    # Direct-to-R2 protected media uploads use a presigned PUT from the browser.
    # CSP must permit only the configured private-storage endpoint; opening connect-src
    # to arbitrary HTTPS hosts would weaken the XSS/data-exfiltration boundary.
    s3_endpoint = os.getenv("S3_ENDPOINT_URL", "").strip()
    if s3_endpoint:
        parsed_s3 = urlparse(s3_endpoint)
        if parsed_s3.scheme == "https" and parsed_s3.hostname:
            connect_sources.append(f"https://{parsed_s3.hostname}")
    response.headers["Content-Security-Policy"] = (
        f"default-src 'self'; img-src {resource_sources} data:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; "
        f"script-src 'self'; frame-src {frame_sources}; media-src {resource_sources} blob:; "
        f"connect-src {' '.join(dict.fromkeys(connect_sources))}; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests"
    )
    path = request.url.path
    if path.startswith("/static/"):
        # Static filenames are human-readable rather than content hashes. Keep a
        # short browser TTL so a deployment can never strand users on stale CSS/JS;
        # Cloudflare's Worker adds a deployment-versioned edge cache separately.
        response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    elif path == "/":
        # The public homepage contains operational links (official class groups).
        # Never serve a stale HTML shell after a deployment through browser/CDN caches.
        response.headers["Cache-Control"] = "no-store, no-cache, max-age=0, must-revalidate"
        response.headers["Cloudflare-CDN-Cache-Control"] = "no-store"
        response.headers["CDN-Cache-Control"] = "no-store"
        response.headers["Surrogate-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Mostashar-Release"] = "V96-WHEEL-TYPOGRAPHY-REFRESH-20260818-01"
    elif path.startswith(("/admin", "/lesson", "/protected", "/dashboard", "/support", "/notifications", "/account")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow, noarchive"
    else:
        response.headers["Cache-Control"] = "private, max-age=60"
    if os.getenv("ENV") == "production":
        hsts = "max-age=31536000"
        include_subdomains = os.getenv("HSTS_INCLUDE_SUBDOMAINS", "false").lower() in {"1", "true", "yes", "on"}
        preload = os.getenv("HSTS_PRELOAD", "false").lower() in {"1", "true", "yes", "on"}
        if include_subdomains:
            hsts += "; includeSubDomains"
            if preload:
                hsts += "; preload"
        response.headers["Strict-Transport-Security"] = hsts
    return response

from .request_context import (
    client_ip, session_record as _session_record, current_user, require_user,
    require_role, template_context as ctx, audit,
)


def award_points(db: Session, user_id: int, points: int, reason: str, ref_type: str = "", ref_id: int | None = None):
    return runtime_award_points(db, user_id, points, reason, ref_type, ref_id)




def validated_video_url(value: str) -> str:
    return runtime_validated_video_url(value, is_production=IS_PRODUCTION)


def _is_direct_video_source(value: str) -> bool:
    try:
        path = (urlparse(value or "").path or "").lower()
    except Exception:
        return False
    return path.endswith((".mp4", ".webm"))

def _direct_video_proxy_enabled() -> bool:
    return runtime_direct_video_proxy_enabled(is_production=IS_PRODUCTION)


def _video_token_ttl() -> int:
    try:
        value = int(os.getenv("VIDEO_TOKEN_TTL_SECONDS", "7200"))
    except ValueError:
        value = 7200
    return max(900, min(value, 14400))

def _safe_range_header(value: str | None) -> str:
    return runtime_safe_range_header(value)


def authorized_for_course(db: Session, user: User, course_id: int):
    return access_authorized_for_course(db, user, course_id)

SUPPORTED_REEL_HOSTS = {
    "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com", "fb.watch",
    "tiktok.com", "www.tiktok.com", "youtube.com", "www.youtube.com", "youtu.be",
}


SUPPORTED_LIVE_PROVIDERS = {"zoom", "meet", "teams", "youtube", "custom"}
LIVE_PROVIDER_HOSTS = {
    "zoom": {"zoom.us", "zoom.com"},
    "meet": {"meet.google.com"},
    "teams": {"teams.microsoft.com", "teams.live.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
}

def _safe_live_url(value: str, provider: str = "custom") -> str:
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











GRADE_ORDER = ["الصف الأول الثانوي", "الصف الثاني الثانوي عام", "الصف الثاني بكالوريا", "الصف الثالث الثانوي"]












































def _lesson_access_state(db: Session, user: User, lesson: Lesson, now: datetime | None = None) -> dict:
    return access_lesson_access_state(db, user, lesson, now)

def _lesson_unlocked(db: Session, user: User, lesson: Lesson) -> bool:
    return bool(_lesson_access_state(db, user, lesson)["unlocked"])

def _course_completion_status(db: Session, user_id: int, course_id: int) -> dict:
    return runtime_course_completion_status(db, user_id, course_id)


def _issue_course_certificate(db: Session, user_id: int, course_id: int) -> CourseCertificate | None:
    return runtime_issue_course_certificate(db, user_id, course_id)



def _study_tokens(value: str) -> set[str]:
    return service_study_tokens(value)

def _smart_study_answer(db: Session, lesson: Lesson, question: str, user: User | None = None, mode: str = "explain") -> tuple[str, str]:
    return service_smart_study_answer(db, lesson, question, user, mode)

def _render_lesson_page(request: Request, db: Session, lesson: Lesson, u: User, *, assistant_question: str = "", assistant_answer: str = ""):
    return service_render_lesson_page(request, db, lesson, u, assistant_question=assistant_question, assistant_answer=assistant_answer, is_production=IS_PRODUCTION)



def _communication_recipients(db: Session, audience_type: str, audience_value: str = ""):
    q = db.query(User).filter(User.role == "student", User.is_active == True)
    audience_value = (audience_value or "").strip()
    if audience_type == "grade":
        ids = [x.user_id for x in db.query(StudentProfile).filter(StudentProfile.grade == audience_value).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "course":
        try: course_id = int(audience_value)
        except (TypeError, ValueError): return []
        now = datetime.utcnow()
        ids = [e.user_id for e in db.query(Enrollment).filter(Enrollment.course_id == course_id, Enrollment.active == True, or_(Enrollment.expires_at == None, Enrollment.expires_at > now)).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "expiring":
        now = datetime.utcnow(); soon = now + timedelta(days=7)
        ids = [x.user_id for x in db.query(Subscription).filter(Subscription.status == "active", Subscription.ends_at != None, Subscription.ends_at > now, Subscription.ends_at <= soon).all()]
        return q.filter(User.id.in_(ids)).all() if ids else []
    if audience_type == "inactive":
        try: days=max(1,min(int(audience_value or "3"),30))
        except ValueError: days=3
        cutoff=datetime.utcnow()-timedelta(days=days); last_map=_student_last_activity_map(db)
        return [s for s in q.all() if not last_map.get(s.id) or last_map[s.id] < cutoff]
    if audience_type == "overdue_homework":
        now = datetime.utcnow()
        overdue = db.query(Homework).filter(Homework.due_at != None, Homework.due_at < now).all()
        if not overdue: return []
        course_ids = {h.course_id for h in overdue}
        due_ids = {h.id for h in overdue}
        enrolled = db.query(Enrollment).filter(Enrollment.course_id.in_(course_ids), Enrollment.active == True).all()
        submitted = {(x.student_id, x.homework_id) for x in db.query(HomeworkSubmission).filter(HomeworkSubmission.homework_id.in_(due_ids)).all()}
        h_by_course = {}
        for h in overdue: h_by_course.setdefault(h.course_id, []).append(h.id)
        ids = {e.user_id for e in enrolled if any((e.user_id, hid) not in submitted for hid in h_by_course.get(e.course_id, []))}
        return q.filter(User.id.in_(ids)).all() if ids else []
    return q.all()

def _send_message_webhook(channel: str, phone: str, title: str, body: str):
    env_map = {"sms": "MESSAGE_SMS_WEBHOOK_URL", "whatsapp": "WHATSAPP_MESSAGE_WEBHOOK_URL", "push": "PUSH_MESSAGE_WEBHOOK_URL"}
    raw_url = os.getenv(env_map.get(channel, ""), "").strip()
    if not raw_url:
        return "not_configured", "مزود القناة غير مهيأ"
    try:
        url = _safe_outbound_webhook_url(raw_url)
    except ValueError:
        return "failed", "عنوان مزود القناة غير آمن"
    if channel in {"sms", "whatsapp"} and not phone:
        return "skipped", "لا يوجد رقم هاتف محفوظ"
    try:
        import httpx
        token = os.getenv("MESSAGE_WEBHOOK_TOKEN", "").strip()
        headers = {"Content-Type":"application/json"}
        if token: headers["Authorization"] = f"Bearer {token}"
        payload = {"channel": channel, "phone": phone, "title": title, "message": body}
        r = httpx.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return "sent", "تم التسليم لمزود الرسائل"
    except Exception as exc:
        return "failed", str(exc)[:420]

def _student_last_activity(db: Session, user_id: int):
    return service_student_last_activity(db, user_id)

def _student_last_activity_map(db: Session):
    return service_student_last_activity_map(db)

def _student_weekly_attendance(db: Session, user_id: int, days: int = 7):
    return service_student_weekly_attendance(db, user_id, days)










def _student_live_classes(db: Session, user_id: int, days_before: int = 7, days_after: int = 21, course_ids: list[int] | None = None):
    return service_student_live_classes(db, user_id, days_before, days_after, course_ids)












# --- UI V19: groups / cohorts ---




































def _student_performance_rows(db: Session):
    return service_student_performance_rows(db)


























app.state.resolve_user = current_user
# V64 router migration bridge. Shared web helpers stay centralized while route
# modules are moved out of main.py; later releases can move these helpers too.
app.state.require_user = require_user
app.state.require_role = require_role
app.state.template_context = ctx
app.state.render_template = render_template
app.state.audit = audit

from .routers.learning_runtime import router as learning_runtime_router

app.include_router(pwa_router)
app.include_router(system_router)
app.include_router(api_v1_router)
app.include_router(support_router)
app.include_router(media_router)
app.include_router(commerce_router)
app.include_router(auth_router)
app.include_router(courses_router)
app.include_router(communications_router)
app.include_router(reports_router)
app.include_router(admin_users_router)
app.include_router(admin_security_router)
app.include_router(parents_router)
app.include_router(community_router)
app.include_router(homepage_router)
app.include_router(academic_content_router)
app.include_router(remediation_router)
app.include_router(assessments_admin_router)
app.include_router(push_notifications_router)
app.include_router(activation_codes_router)
app.include_router(dashboards_router)
app.include_router(course_categories_router)
app.include_router(student_experience_router)
app.include_router(system_admin_router)
app.include_router(certificates_router)
app.include_router(english_tools_router)
app.include_router(discussion_admin_router)
app.include_router(learning_runtime_router)







