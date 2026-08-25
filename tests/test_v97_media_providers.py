"""Tests for app.media_providers — URL detection for video and document providers.

Covers spec section 16's testing checklist: YouTube (long + short URL), Cloudflare
Stream, Bunny, invalid video URL, R2 document, Google Drive document, invalid
Google Drive URL, and malicious lookalike domains (SSRF / spoofing guard).
"""
import pytest

from app.media_providers import (
    UnsupportedMediaProviderError,
    build_external_document_key,
    detect_document_provider,
    detect_video_provider,
    parse_external_document_key,
)


# --- Video: YouTube ---

def test_youtube_watch_url():
    d = detect_video_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert d.provider == "youtube"
    assert d.identifier == "dQw4w9WgXcQ"
    assert "youtube-nocookie.com/embed/dQw4w9WgXcQ" in d.embed_url


def test_youtube_short_url():
    d = detect_video_provider("https://youtu.be/dQw4w9WgXcQ")
    assert d.provider == "youtube"
    assert d.identifier == "dQw4w9WgXcQ"


def test_youtube_embed_url():
    d = detect_video_provider("https://www.youtube.com/embed/dQw4w9WgXcQ")
    assert d.provider == "youtube"


def test_youtube_shorts_url():
    d = detect_video_provider("https://www.youtube.com/shorts/dQw4w9WgXcQ")
    assert d.provider == "youtube"


def test_youtube_lookalike_domain_rejected():
    # youtube.com.evil.com must NOT be treated as youtube.com
    with pytest.raises(UnsupportedMediaProviderError):
        detect_video_provider("https://youtube.com.evil.com/watch?v=dQw4w9WgXcQ")


# --- Video: Bunny ---

def test_bunny_embed_url():
    d = detect_video_provider("https://iframe.mediadelivery.net/embed/12345/abcd1234-ef01-4321-9999-abcdefabcdef")
    assert d.provider == "bunny"
    assert d.library_id == "12345"
    assert d.identifier == "abcd1234-ef01-4321-9999-abcdefabcdef"


def test_bunny_cdn_direct_link_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_video_provider("https://myzone.b-cdn.net/some/video.m3u8")


# --- Video: invalid / unsupported ---

def test_invalid_video_url_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_video_provider("not a url")


def test_http_video_url_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_video_provider("http://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_vimeo_url_is_not_auto_detected():
    # Vimeo/Mux/custom stay manual-provider selections; detection should decline
    # rather than guess, so the admin UI falls back to the manual selector.
    with pytest.raises(UnsupportedMediaProviderError):
        detect_video_provider("https://vimeo.com/123456789")


# --- Documents: R2 ---

def test_r2_document_url():
    d = detect_document_provider("https://my-bucket.abc123.r2.cloudflarestorage.com/lessons/file.pdf")
    assert d.provider == "r2"
    assert d.identifier == "lessons/file.pdf"


# --- Documents: Google Drive ---

def test_google_drive_file_url():
    d = detect_document_provider("https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view?usp=sharing")
    assert d.provider == "google_drive"
    assert d.identifier == "1AbCdEfGhIjKlMnOpQrStUvWxYz"


def test_google_drive_open_id_query_url():
    d = detect_document_provider("https://drive.google.com/open?id=1AbCdEfGhIjKlMnOpQrStUvWxYz")
    assert d.provider == "google_drive"
    assert d.identifier == "1AbCdEfGhIjKlMnOpQrStUvWxYz"


def test_google_drive_lookalike_domain_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_document_provider("https://drive.google.com.evil.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view")


def test_invalid_google_drive_url_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_document_provider("https://drive.google.com/file/d/short/view")


def test_invalid_document_url_rejected():
    with pytest.raises(UnsupportedMediaProviderError):
        detect_document_provider("https://example.com/not-a-supported-provider.pdf")


# --- Storage key helpers (per-lesson scoping to respect MediaAsset.storage_key UNIQUE) ---

def test_external_document_key_roundtrip():
    key = build_external_document_key("1AbCdEfGhIjKlMnOpQrStUvWxYz", 42)
    assert key == "1AbCdEfGhIjKlMnOpQrStUvWxYz#lesson-42"
    assert parse_external_document_key(key) == "1AbCdEfGhIjKlMnOpQrStUvWxYz"


def test_external_document_key_differs_per_lesson():
    # Same external file linked from two lessons must not collide on the
    # table-wide UNIQUE(storage_key) constraint.
    key_a = build_external_document_key("same-file-id", 1)
    key_b = build_external_document_key("same-file-id", 2)
    assert key_a != key_b

def test_youtube_embed_url_has_required_params():
    d = detect_video_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    for param in ("modestbranding=1", "rel=0", "playsinline=1", "iv_load_policy=3"):
        assert param in d.embed_url


def test_youtube_embed_url_excludes_disallowed_params():
    d = detect_video_provider("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "controls=0" not in d.embed_url
    assert "disablekb=1" not in d.embed_url


def test_external_document_key_roundtrip_with_full_url():
    url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOpQrStUvWxYz/view"
    key = build_external_document_key(url, 42)
    assert key == f"{url}#lesson-42"
    assert parse_external_document_key(key) == url