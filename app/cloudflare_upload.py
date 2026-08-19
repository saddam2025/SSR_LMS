"""Cloudflare Stream direct/resumable upload integration.

The browser receives a one-time tus endpoint and uploads the lecture directly
to Cloudflare Stream. The API token never leaves the server.
"""

from __future__ import annotations

import base64
import os
import re
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx


_UID_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
_ACCOUNT_RE = re.compile(r"^[a-fA-F0-9]{32}$")
_UPLOAD_HOSTS = ("upload.videodelivery.net",)
_DEFAULT_MAX_BYTES = 30 * 1024 * 1024 * 1024
_DEFAULT_CHUNK_BYTES = 10 * 1024 * 1024


class StreamUploadError(RuntimeError):
    def __init__(self, status_code: int, public_message: str):
        super().__init__(public_message)
        self.status_code = status_code
        self.public_message = public_message


def stream_upload_ready() -> bool:
    account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_STREAM_API_TOKEN", "").strip()
    return bool(_ACCOUNT_RE.fullmatch(account_id) and len(token) >= 20)




def allowed_origins() -> list[str]:
    """Return Cloudflare Stream Allowed Origins as domain[:port] entries."""
    raw = os.getenv("STREAM_ALLOWED_ORIGINS", "").strip()
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        public = os.getenv("PUBLIC_BASE_URL", "").strip()
        if public:
            try:
                parsed = urlparse(public)
                if parsed.hostname:
                    host = parsed.hostname.lower()
                    if parsed.port and not ((parsed.scheme == "https" and parsed.port == 443) or (parsed.scheme == "http" and parsed.port == 80)):
                        host = f"{host}:{parsed.port}"
                    values = [host]
            except ValueError:
                values = []
    result: list[str] = []
    for value in values:
        candidate = value
        if "://" in value:
            try:
                parsed = urlparse(value)
                candidate = (parsed.hostname or "").lower()
                if parsed.port and not ((parsed.scheme == "https" and parsed.port == 443) or (parsed.scheme == "http" and parsed.port == 80)):
                    candidate = f"{candidate}:{parsed.port}"
            except ValueError:
                continue
        candidate = candidate.strip().lower().rstrip("/")
        if not candidate or "/" in candidate or len(candidate) > 253:
            continue
        if candidate not in result:
            result.append(candidate)
    return result[:20]

def max_upload_bytes() -> int:
    try:
        configured = int(os.getenv("CF_STREAM_MAX_UPLOAD_BYTES", str(_DEFAULT_MAX_BYTES)))
    except ValueError:
        configured = _DEFAULT_MAX_BYTES
    return max(5 * 1024 * 1024, min(configured, _DEFAULT_MAX_BYTES))


def upload_chunk_bytes() -> int:
    try:
        configured = int(os.getenv("CF_STREAM_TUS_CHUNK_BYTES", str(_DEFAULT_CHUNK_BYTES)))
    except ValueError:
        configured = _DEFAULT_CHUNK_BYTES
    minimum = 5 * 1024 * 1024
    maximum = 200 * 1024 * 1024
    configured = max(minimum, min(configured, maximum))
    block = 256 * 1024
    return max(minimum, (configured // block) * block)


def max_duration_seconds() -> int:
    try:
        configured = int(os.getenv("CF_STREAM_MAX_DURATION_SECONDS", "21600"))
    except ValueError:
        configured = 21600
    return max(60, min(configured, 86400))


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _credentials() -> tuple[str, str]:
    account_id = os.getenv("CF_ACCOUNT_ID", "").strip()
    token = os.getenv("CF_STREAM_API_TOKEN", "").strip()
    if not _ACCOUNT_RE.fullmatch(account_id) or len(token) < 20:
        raise StreamUploadError(
            503,
            "رفع المحاضرات غير مهيأ. أضف CF_ACCOUNT_ID وCF_STREAM_API_TOKEN بصلاحية Stream Edit.",
        )
    return account_id, token


def _provider_error(status_code: int) -> StreamUploadError:
    if status_code in {401, 403}:
        return StreamUploadError(502, "مفتاح Cloudflare Stream غير صالح أو لا يملك صلاحية Stream Edit.")
    if status_code == 413:
        return StreamUploadError(413, "حجم المحاضرة أكبر من الحد المتاح في Cloudflare Stream.")
    if status_code == 429:
        return StreamUploadError(429, "تم الوصول مؤقتًا إلى حد رفع أو معالجة الفيديوهات. حاول بعد قليل.")
    if status_code >= 500:
        return StreamUploadError(502, "خدمة رفع الفيديو غير متاحة مؤقتًا. حاول مرة أخرى.")
    return StreamUploadError(502, "تعذر إنشاء رابط رفع آمن للمحاضرة.")


def _validate_upload_location(location: str) -> str:
    try:
        parsed = urlparse(location)
    except ValueError:
        parsed = None
    host = (parsed.hostname or "").lower() if parsed else ""
    if not parsed or parsed.scheme != "https" or not any(host == item or host.endswith("." + item) for item in _UPLOAD_HOSTS):
        raise StreamUploadError(502, "أعاد مزود الفيديو رابط رفع غير صالح.")
    return location


def _uid_from_response(location: str, headers) -> str:
    uid = (headers.get("stream-media-id") or headers.get("Stream-Media-Id") or "").strip()
    if not _UID_RE.fullmatch(uid):
        candidates = [item for item in urlparse(location).path.split("/") if item]
        uid = next((item for item in reversed(candidates) if _UID_RE.fullmatch(item)), "")
    if not _UID_RE.fullmatch(uid):
        raise StreamUploadError(502, "تعذر تحديد معرّف المحاضرة بعد إنشاء رابط الرفع.")
    return uid


def create_tus_upload(*, file_name: str, file_size: int, content_type: str, creator: str) -> dict:
    account_id, token = _credentials()
    if file_size <= 0 or file_size > max_upload_bytes():
        raise StreamUploadError(413, "حجم ملف المحاضرة خارج الحد المسموح.")

    expiry = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    duration = max_duration_seconds()
    metadata_items = [
        f"name {_b64(file_name)}",
        f"filetype {_b64(content_type or 'application/octet-stream')}",
        f"maxDurationSeconds {_b64(str(duration))}",
        "requiresignedurls",
        f"expiry {_b64(expiry)}",
    ]
    origins = allowed_origins()
    if origins:
        metadata_items.append(f"allowedorigins {_b64(json.dumps(origins, separators=(',', ':')))}")
    metadata = ",".join(metadata_items)
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream?direct_user=true"
    headers = {
        "Authorization": f"Bearer {token}",
        "Tus-Resumable": "1.0.0",
        "Upload-Length": str(file_size),
        "Upload-Metadata": metadata,
        "Upload-Creator": creator[:64],
    }
    try:
        response = httpx.post(endpoint, headers=headers, timeout=20.0, follow_redirects=False)
    except httpx.HTTPError as exc:
        raise StreamUploadError(502, "تعذر الاتصال بخدمة رفع الفيديو. تحقق من الإنترنت وحاول مرة أخرى.") from exc
    if response.status_code not in {200, 201}:
        raise _provider_error(response.status_code)
    location = _validate_upload_location(response.headers.get("Location", ""))
    uid = _uid_from_response(location, response.headers)
    return {
        "upload_url": location,
        "uid": uid,
        "chunk_size": upload_chunk_bytes(),
        "max_bytes": max_upload_bytes(),
        "expires_at": expiry,
    }


def stream_video_details(uid: str) -> dict:
    if not _UID_RE.fullmatch(uid or ""):
        raise StreamUploadError(400, "معرّف الفيديو غير صالح.")
    account_id, token = _credentials()
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{uid}"
    try:
        response = httpx.get(endpoint, headers={"Authorization": f"Bearer {token}"}, timeout=20.0)
    except httpx.HTTPError as exc:
        raise StreamUploadError(502, "تعذر قراءة حالة معالجة المحاضرة.") from exc
    if response.status_code != 200:
        raise _provider_error(response.status_code)
    try:
        payload = response.json()
        result = payload.get("result") or {}
    except (ValueError, AttributeError) as exc:
        raise StreamUploadError(502, "استجابة حالة الفيديو غير صالحة.") from exc
    if result.get("uid") != uid:
        raise StreamUploadError(502, "استجابة حالة الفيديو لا تطابق المحاضرة.")
    return result


def enforce_signed_video(uid: str) -> None:
    if not _UID_RE.fullmatch(uid or ""):
        raise StreamUploadError(400, "معرّف الفيديو غير صالح.")
    account_id, token = _credentials()
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/stream/{uid}"
    try:
        protection = {"uid": uid, "requireSignedURLs": True}
        origins = allowed_origins()
        if origins:
            protection["allowedOrigins"] = origins
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=protection,
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise StreamUploadError(502, "تعذر تفعيل الحماية الخاصة للمحاضرة.") from exc
    if response.status_code not in {200, 201}:
        raise _provider_error(response.status_code)


def valid_stream_uid(value: str) -> bool:
    return bool(_UID_RE.fullmatch(value or ""))
