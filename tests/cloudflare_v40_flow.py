import base64
import hashlib
import hmac
import os
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///./cloudflare_v40_test.db")
os.environ.pop("ENV", None)
os.environ["CF_EDGE_SIGNING_SECRET"] = "edge-test-secret-" + ("x" * 48)
os.environ["VIDEO_ALLOWED_HOSTS"] = "cloudflarestream.com,videodelivery.net"

from fastapi.testclient import TestClient
from app.cloudflare_stream import extract_stream_uid, sign_stream_grant, stream_embed_path
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Enrollment, Lesson, LessonVideoProfile, User
from app.production import production_status
from app.seed import run as seed


uid = "a1b2c3d4e5f678901234567890abcdef"
stream_url = f"https://customer-demo.cloudflarestream.com/{uid}/iframe"
assert extract_stream_uid(stream_url) == uid
assert extract_stream_uid(f"https://iframe.videodelivery.net/{uid}") == uid
assert extract_stream_uid(f"https://cloudflarestream.com.evil.test/{uid}/iframe") is None
assert extract_stream_uid("https://example.test/not-stream") is None

grant = sign_stream_grant(uid, 7, 11)
payload_part, signature_part = grant.split(".")
expected = hmac.new(
    os.environ["CF_EDGE_SIGNING_SECRET"].encode(),
    payload_part.encode("ascii"),
    hashlib.sha256,
).digest()
padding = "=" * ((4 - len(signature_part) % 4) % 4)
assert hmac.compare_digest(expected, base64.urlsafe_b64decode(signature_part + padding))
assert stream_embed_path(stream_url, 7, 11).startswith(f"/_edge/stream/{uid}?grant=")

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
seed()
db = SessionLocal()
student = db.query(User).filter_by(role="student").first()
lesson = db.query(Lesson).filter_by(published=True).first()
assert student and lesson
if not db.query(Enrollment).filter_by(user_id=student.id, course_id=lesson.course_id).first():
    db.add(Enrollment(user_id=student.id, course_id=lesson.course_id, active=True))
lesson.video_url = stream_url
db.add(LessonVideoProfile(lesson_id=lesson.id, provider="cloudflare", stream_type="hls", drm_mode="signed", processing_status="ready"))
db.commit()
lesson_id = lesson.id
db.close()

client = TestClient(app)
response = client.get("/login")
csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
response = client.post(
    "/login",
    data={"email": "student@ragab-seddik.local", "password": "Student123!", "csrf": csrf},
    follow_redirects=False,
)
assert response.status_code in (302, 303)
response = client.get(f"/lesson/{lesson_id}")
assert response.status_code == 200, response.text
assert f'iframe src="/_edge/stream/{uid}?grant=' in response.text
assert f'iframe src="{stream_url}"' not in response.text
csp = response.headers["content-security-policy"]
assert "https://*.cloudflarestream.com" in csp and "https://*.videodelivery.net" in csp

os.environ.update({
    "ENV": "production",
"REQUIRE_STAFF_MFA": "true",
    "CLOUDFLARE_DEPLOYMENT": "true",
    "PUBLIC_BASE_URL": "https://api.ragab-seddik.com",
    "APP_SECRET": "a" * 64,
    "DATABASE_URL": "postgresql://user:pass@db.example.test/mostashar",
    "REDIS_URL": "rediss://redis.example.test:6379/0",
    "ADMIN_EMAIL": "admin@ragab-seddik.com",
    "ADMIN_PASSWORD": "StrongUniqueAdminPass123!",
    "ALLOWED_HOSTS": "api.ragab-seddik.com,ragab-seddik.com,www.ragab-seddik.com,healthcheck.railway.app",
    "FRONTEND_PRIMARY_ORIGIN": "https://student.ragab-seddik.com",
    "FRONTEND_ORIGINS": "https://student.ragab-seddik.com",
    "STORAGE_BACKEND": "s3",
    "S3_ENDPOINT_URL": "https://accountid.r2.cloudflarestorage.com",
    "S3_BUCKET": "mostashar-private",
    "S3_ACCESS_KEY_ID": "test-access-key",
    "S3_SECRET_ACCESS_KEY": "test-secret-key",
    "CF_ACCOUNT_ID": "a" * 32,
    "CF_STREAM_API_TOKEN": "token-" + ("b" * 40),
    "CF_STREAM_CUSTOMER_CODE": "test-customer-code",
    "ALLOW_DIRECT_VIDEO_PROXY": "false",
})
status = production_status()
assert status["required_ok"], status
assert status["required"]["cloudflare_r2_storage"]
assert status["required"]["cloudflare_stream_hosts"]
assert status["required"]["cloudflare_stream_upload"]
print("CLOUDFLARE V40 FLOW OK")
