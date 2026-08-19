import base64
import json
import os
import time
from pathlib import Path

from app import cloudflare_upload
from app.cloudflare_stream import sign_stream_grant, stream_grant_ttl

ROOT = Path(__file__).resolve().parents[1]
UID = "a1b2c3d4e5f678901234567890abcdef"


class FakeResponse:
    status_code = 201
    headers = {
        "Location": f"https://upload.videodelivery.net/tus/{UID}",
        "stream-media-id": UID,
    }


def _decode_metadata(header: str) -> dict[str, str | None]:
    result = {}
    for item in header.split(","):
        if " " not in item:
            result[item] = None
            continue
        key, encoded = item.split(" ", 1)
        result[key] = base64.b64decode(encoded).decode("utf-8")
    return result


def test_stream_upload_sets_signed_urls_and_allowed_origins(monkeypatch):
    monkeypatch.setenv("CF_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("CF_STREAM_API_TOKEN", "token-" + "b" * 40)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://ragab-seddik.com")
    monkeypatch.setenv("STREAM_ALLOWED_ORIGINS", "ragab-seddik.com,www.ragab-seddik.com")
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(cloudflare_upload.httpx, "post", fake_post)
    provisioned = cloudflare_upload.create_tus_upload(
        file_name="lesson.mp4",
        file_size=10 * 1024 * 1024,
        content_type="video/mp4",
        creator="mostashar-u1-l1",
    )
    assert provisioned["uid"] == UID
    metadata = _decode_metadata(captured["headers"]["Upload-Metadata"])
    assert "requiresignedurls" in metadata
    assert json.loads(metadata["allowedorigins"]) == ["ragab-seddik.com", "www.ragab-seddik.com"]


def test_stream_finalize_reasserts_signed_urls_and_origins(monkeypatch):
    monkeypatch.setenv("CF_ACCOUNT_ID", "a" * 32)
    monkeypatch.setenv("CF_STREAM_API_TOKEN", "token-" + "b" * 40)
    monkeypatch.setenv("STREAM_ALLOWED_ORIGINS", "ragab-seddik.com")
    captured = {}

    class R:
        status_code = 200

    def fake_post(url, **kwargs):
        captured.update(kwargs)
        return R()

    monkeypatch.setattr(cloudflare_upload.httpx, "post", fake_post)
    cloudflare_upload.enforce_signed_video(UID)
    assert captured["json"]["requireSignedURLs"] is True
    assert captured["json"]["allowedOrigins"] == ["ragab-seddik.com"]


def test_edge_grant_default_is_short_lived(monkeypatch):
    monkeypatch.setenv("CF_EDGE_SIGNING_SECRET", "s" * 48)
    monkeypatch.setenv("STREAM_EDGE_GRANT_TTL_SECONDS", "90")
    assert stream_grant_ttl() == 90
    grant = sign_stream_grant(UID, 7, 11)
    payload_part = grant.split(".", 1)[0]
    padding = "=" * ((4 - len(payload_part) % 4) % 4)
    payload = base64.urlsafe_b64decode(payload_part + padding).decode("utf-8")
    expires = int(payload.split("|")[4])
    remaining = expires - int(time.time())
    assert 85 <= remaining <= 90


def test_stream_worker_is_packaged_and_uses_binding_hmac_and_no_store():
    worker = (ROOT / "cloudflare" / "stream-edge" / "src" / "index.js").read_text(encoding="utf-8")
    wrangler = (ROOT / "cloudflare" / "stream-edge" / "wrangler.toml.example").read_text(encoding="utf-8")
    assert "crypto.subtle.verify" in worker
    assert "env.STREAM.video(uid).generateToken()" in worker
    assert "expiresAt > now + 300" in worker
    assert "cache-control': 'no-store" in worker
    assert "[stream]" in wrangler and 'binding = "STREAM"' in wrangler
    assert "CF_EDGE_SIGNING_SECRET =" not in wrangler
