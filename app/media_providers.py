"""Multi-provider media URL detection and normalization.

Classifies a teacher-submitted video or document URL into a known provider
without ever fetching the URL (no SSRF surface). Host matching uses strict
urlparse comparisons (exact host or proper subdomain), never `in`/substring
checks, so lookalike domains such as youtube.com.evil.com are rejected the
same way app/cloudflare_stream.py already validates Stream hosts.

VIDEO
    Cloudflare Stream -> delegates to cloudflare_stream.extract_stream_uid()
    YouTube           -> watch / youtu.be / embed / shorts URLs
    Bunny Stream      -> iframe.mediadelivery.net embed URLs

DOCUMENTS
    R2                -> *.r2.cloudflarestorage.com URLs
    Google Drive      -> drive.google.com share/view URLs (public/shared only)

Nothing here requires a schema migration: video provider is stored in the
existing LessonVideoProfile.provider column, and document provider re-uses the
existing MediaAsset.provider / MediaAsset.storage_key columns.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

from .cloudflare_stream import extract_stream_uid

VIDEO_PROVIDERS = ("cloudflare", "bunny", "youtube")
DOCUMENT_PROVIDERS = ("r2", "google_drive")

_YT_HOSTS = ("youtube.com", "youtube-nocookie.com")
_YT_SHORT_HOSTS = ("youtu.be",)
_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_BUNNY_IFRAME_HOSTS = ("iframe.mediadelivery.net",)
_BUNNY_CDN_HOSTS = ("b-cdn.net",)
_BUNNY_PATH_RE = re.compile(r"^/(?:embed/)?(?P<library>\d+)/(?P<video>[A-Za-z0-9-]{8,64})/?$")

_GDRIVE_HOSTS = ("drive.google.com",)
_GDRIVE_FILE_RE = re.compile(r"^/file/d/(?P<id>[A-Za-z0-9_-]{10,100})")
_GDRIVE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,100}$")

_EXTERNAL_DOC_KEY_SEP = "#lesson-"


class UnsupportedMediaProviderError(ValueError):
    """Raised when a URL doesn't match any supported provider.

    `kind` is "video" or "document" so callers can show the right error copy
    from section 10 of the spec without string-matching the message.
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind


def _host_matches(host: str, allowed: tuple[str, ...]) -> bool:
    return any(host == d or host.endswith("." + d) for d in allowed)


@dataclass(frozen=True)
class VideoDetection:
    provider: str                 # "cloudflare" | "bunny" | "youtube"
    identifier: str               # stream uid / bunny video id / youtube video id
    embed_url: str                # safe <iframe src>; empty for cloudflare (uses signed grant instead)
    library_id: str | None = None  # bunny only


def detect_video_provider(url: str) -> VideoDetection:
    """Classify a teacher-submitted video URL. Never fetches the URL."""
    url = (url or "").strip()
    if not url:
        raise UnsupportedMediaProviderError("video", "رابط الفيديو مطلوب")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise UnsupportedMediaProviderError("video", "رابط الفيديو غير صالح")
    if parsed.scheme != "https":
        raise UnsupportedMediaProviderError("video", "رابط الفيديو يجب أن يكون HTTPS")
    host = (parsed.hostname or "").lower()

    # Cloudflare Stream: reuse the existing, already-hardened UID extractor so
    # we have exactly one source of truth for what counts as a valid Stream URL.
    uid = extract_stream_uid(url)
    if uid:
        return VideoDetection(provider="cloudflare", identifier=uid, embed_url="")

    # YouTube
    if _host_matches(host, _YT_SHORT_HOSTS):
        vid = parsed.path.strip("/").split("/")[0]
        if _YT_ID_RE.fullmatch(vid or ""):
            return VideoDetection(
                provider="youtube", identifier=vid,
                embed_url=f"https://www.youtube-nocookie.com/embed/{vid}?modestbranding=1&rel=0&playsinline=1&iv_load_policy=3",
            )
        raise UnsupportedMediaProviderError("video", "رابط يوتيوب غير صالح")
    if _host_matches(host, _YT_HOSTS):
        if parsed.path == "/watch":
            vid = (parse_qs(parsed.query).get("v") or [""])[0]
        elif parsed.path.startswith("/embed/"):
            vid = parsed.path.split("/embed/", 1)[1].split("/")[0]
        elif parsed.path.startswith("/shorts/"):
            vid = parsed.path.split("/shorts/", 1)[1].split("/")[0]
        else:
            vid = ""
        if _YT_ID_RE.fullmatch(vid or ""):
            return VideoDetection(
                provider="youtube", identifier=vid,
                embed_url=f"https://www.youtube-nocookie.com/embed/{vid}?modestbranding=1&rel=0&playsinline=1&iv_load_policy=3",
            )
        raise UnsupportedMediaProviderError("video", "رابط يوتيوب غير صالح")

    # Bunny Stream
    if _host_matches(host, _BUNNY_IFRAME_HOSTS):
        m = _BUNNY_PATH_RE.match(parsed.path)
        if m:
            library, video = m.group("library"), m.group("video")
            return VideoDetection(
                provider="bunny", identifier=video, library_id=library,
                embed_url=f"https://iframe.mediadelivery.net/embed/{library}/{video}?autoplay=false",
            )
        raise UnsupportedMediaProviderError("video", "رابط Bunny Stream غير صالح")
    if _host_matches(host, _BUNNY_CDN_HOSTS):
        raise UnsupportedMediaProviderError(
            "video", "استخدم رابط تضمين Bunny Stream (iframe.mediadelivery.net) بدلًا من رابط CDN المباشر",
        )

    raise UnsupportedMediaProviderError(
        "video",
        "رابط فيديو غير مدعوم تلقائيًا. المزودات المكتشفة تلقائيًا: YouTube، Cloudflare Stream، Bunny Stream. "
        "يمكنك اختيار Vimeo/Mux/Custom يدويًا من إعدادات الفيديو إذا كان الرابط من مزود آخر.",
    )


@dataclass(frozen=True)
class DocumentDetection:
    provider: str        # "r2" | "google_drive"
    identifier: str      # R2 object key, or Google Drive file id
    normalized_url: str


def detect_document_provider(url: str) -> DocumentDetection:
    """Classify a teacher-submitted document URL. Never fetches the URL."""
    url = (url or "").strip()
    if not url:
        raise UnsupportedMediaProviderError("document", "رابط المستند مطلوب")
    try:
        parsed = urlparse(url)
    except ValueError:
        raise UnsupportedMediaProviderError("document", "رابط المستند غير صالح")
    if parsed.scheme != "https":
        raise UnsupportedMediaProviderError("document", "رابط المستند يجب أن يكون HTTPS")
    host = (parsed.hostname or "").lower()

    if host.endswith(".r2.cloudflarestorage.com"):
        key = parsed.path.lstrip("/")
        if not key:
            raise UnsupportedMediaProviderError("document", "رابط R2 غير صالح")
        return DocumentDetection(provider="r2", identifier=key, normalized_url=url)

    if _host_matches(host, _GDRIVE_HOSTS):
        m = _GDRIVE_FILE_RE.match(parsed.path)
        file_id = m.group("id") if m else (parse_qs(parsed.query).get("id") or [""])[0]
        if not _GDRIVE_ID_RE.fullmatch(file_id or ""):
            raise UnsupportedMediaProviderError("document", "تعذر استخراج معرّف ملف Google Drive من الرابط")
        return DocumentDetection(
            provider="google_drive", identifier=file_id,
            normalized_url=f"https://drive.google.com/file/d/{file_id}/view",
        )

    raise UnsupportedMediaProviderError("document", "رابط مستند غير مدعوم. المزودات المدعومة: R2 وGoogle Drive.")


def build_external_document_key(identifier: str, lesson_id: int) -> str:
    """Build a MediaAsset.storage_key for a link-based (non-uploaded) document.

    MediaAsset.storage_key has a table-wide UNIQUE constraint, which is correct
    for randomly generated upload keys but would wrongly block the same shared
    Google Drive/R2 URL being linked from two different lessons. Scoping the key
    to the lesson keeps the existing column/constraint but allows that.
    """
    return f"{identifier}{_EXTERNAL_DOC_KEY_SEP}{int(lesson_id)}"


def parse_external_document_key(storage_key: str) -> str:
    """Inverse of build_external_document_key(); returns the bare identifier."""
    return storage_key.split(_EXTERNAL_DOC_KEY_SEP, 1)[0]