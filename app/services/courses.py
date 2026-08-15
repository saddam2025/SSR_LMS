"""Course/lesson domain helpers introduced in V69."""
import os
from urllib.parse import urlparse
from fastapi import HTTPException


def _is_production() -> bool:
    return os.getenv("ENV") == "production"


def is_direct_video_source(value: str) -> bool:
    try:
        path = (urlparse(value or "").path or "").lower()
    except Exception:
        return False
    return path.endswith((".mp4", ".webm"))


def direct_video_proxy_enabled() -> bool:
    flag = os.getenv("ALLOW_DIRECT_VIDEO_PROXY", "false").strip().lower()
    return not _is_production() or flag in {"1", "true", "yes", "on"}


def validated_video_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise HTTPException(400, "رابط الفيديو يجب أن يكون HTTPS صالحًا")
    allowed = {h.strip().lower() for h in os.getenv("VIDEO_ALLOWED_HOSTS", "").split(",") if h.strip()}
    host = parsed.hostname.lower()
    if _is_production() and not allowed:
        raise HTTPException(503, "إعداد روابط الفيديو غير مكتمل: يجب تحديد VIDEO_ALLOWED_HOSTS في إعدادات الخادم.")
    if allowed and not any(host == h or host.endswith("." + h) for h in allowed):
        raise HTTPException(400, "مزود الفيديو غير موجود في قائمة النطاقات المسموح بها")
    if _is_production() and is_direct_video_source(value) and not direct_video_proxy_enabled():
        raise HTTPException(400, "روابط MP4/WebM الخام غير مسموحة في Production. استخدم مزود Streaming/DRM معتمدًا.")
    return value
