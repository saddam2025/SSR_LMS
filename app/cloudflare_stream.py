"""Cloudflare Stream helpers shared by the FastAPI lesson renderer.

The application never renders the permanent Stream video UID as a playable URL
in production. Instead it creates a short-lived HMAC grant. The Cloudflare
Worker verifies that grant, asks the Stream binding for a signed playback token,
and redirects the iframe to the private player.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import time
from urllib.parse import urlparse


_STREAM_HOST_SUFFIXES = ("cloudflarestream.com", "videodelivery.net")
_UID_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def extract_stream_uid(video_url: str) -> str | None:
    """Return the Stream UID from a supported Cloudflare player URL."""
    try:
        parsed = urlparse((video_url or "").strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not any(host == suffix or host.endswith("." + suffix) for suffix in _STREAM_HOST_SUFFIXES):
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None
    candidate = parts[0]
    return candidate if _UID_RE.fullmatch(candidate) else None


def stream_edge_ready() -> bool:
    secret = os.getenv("CF_EDGE_SIGNING_SECRET", "")
    return len(secret) >= 32


def sign_stream_grant(video_uid: str, lesson_id: int, user_id: int, ttl_seconds: int = 300) -> str:
    """Create a short edge-only grant; this is not the Stream playback token."""
    if not _UID_RE.fullmatch(video_uid or ""):
        raise ValueError("invalid_cloudflare_stream_uid")
    secret = os.getenv("CF_EDGE_SIGNING_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("CF_EDGE_SIGNING_SECRET must be at least 32 characters")
    ttl = max(60, min(int(ttl_seconds), 300))
    expires = int(time.time()) + ttl
    nonce = secrets.token_urlsafe(9)
    payload = f"v1|{video_uid}|{int(lesson_id)}|{int(user_id)}|{expires}|{nonce}".encode("utf-8")
    encoded_payload = _base64url(payload)
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{encoded_payload}.{_base64url(signature)}"


def stream_embed_path(video_url: str, lesson_id: int, user_id: int) -> str | None:
    uid = extract_stream_uid(video_url)
    if not uid or not stream_edge_ready():
        return None
    grant = sign_stream_grant(uid, lesson_id, user_id)
    return f"/_edge/stream/{uid}?grant={grant}"
