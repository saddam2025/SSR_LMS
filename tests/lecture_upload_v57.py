import io
import os
import re
import shutil
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./lecture_upload_v57.db"
os.environ["ENV"] = "test"
os.environ["APP_SECRET"] = "test-secret-change-this"
os.environ["LOCAL_MEDIA_ROOT"] = f"/tmp/mostashar-v57-media-{os.getpid()}"
os.environ["CF_ACCOUNT_ID"] = "a" * 32
os.environ["CF_STREAM_API_TOKEN"] = "token-" + ("b" * 40)

from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app import cloudflare_upload
from app import main
from app.db import Base, SessionLocal, engine
from app.models import Course, Lesson, LessonVideoProfile, MediaAsset
from app.seed import run as seed


UID = "f65014bc6ff5419ea86e7972a047ba22"


def csrf(client, path):
    response = client.get(path)
    assert response.status_code == 200, (path, response.status_code, response.text[:300])
    match = re.search(r'name="csrf" value="([^"]+)"', response.text)
    assert match, path
    return match.group(1)


class FakeResponse:
    def __init__(self, status_code=201, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


# Verify the low-level tus provisioning contract and that the API token is never
# returned to the browser.
captured = {}
original_post = cloudflare_upload.httpx.post


def fake_post(url, **kwargs):
    captured["url"] = url
    captured["headers"] = kwargs["headers"]
    return FakeResponse(
        headers={
            "Location": f"https://upload.videodelivery.net/tus/{UID}",
            "stream-media-id": UID,
        }
    )


cloudflare_upload.httpx.post = fake_post
provisioned = cloudflare_upload.create_tus_upload(
    file_name="محاضرة كبيرة.mp4",
    file_size=600 * 1024 * 1024,
    content_type="video/mp4",
    creator="mostashar-1",
)
cloudflare_upload.httpx.post = original_post
assert provisioned["uid"] == UID
assert provisioned["upload_url"].startswith("https://upload.videodelivery.net/")
assert "CF_STREAM_API_TOKEN" not in str(provisioned)
assert captured["headers"]["Tus-Resumable"] == "1.0.0"
assert captured["headers"]["Upload-Length"] == str(600 * 1024 * 1024)
assert "requiresignedurls" in captured["headers"]["Upload-Metadata"]


media_root = Path(os.environ["LOCAL_MEDIA_ROOT"])
shutil.rmtree(media_root, ignore_errors=True)
Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
seed()
client = TestClient(main.app)

login_csrf = csrf(client, "/login")
login = client.post(
    "/login",
    data={"email": "admin@ragab-seddik.local", "password": "ChangeMe123!", "csrf": login_csrf},
    follow_redirects=False,
)
assert login.status_code in (302, 303)

db = SessionLocal()
course_id = db.query(Course).first().id
db.close()

create = client.post(
    f"/admin/course/{course_id}/lessons",
    data={
        "title": "محاضرة V57",
        "body": "اختبار رفع قابل للاستكمال",
        "video_url": "",
        "csrf": csrf(client, f"/admin/course/{course_id}"),
    },
    follow_redirects=False,
)
assert create.status_code == 303
assert "/admin/lesson/" in create.headers["location"] and "#video-upload" in create.headers["location"]

db = SessionLocal()
lesson = db.query(Lesson).filter_by(title="محاضرة V57").one()
lesson_id = lesson.id
assert lesson.published is False
db.close()

page = client.get(f"/admin/lesson/{lesson_id}/edit")
assert page.status_code == 200
assert "data-stream-upload-form" in page.text
assert "admin-media-upload.js" in page.text

main.create_tus_upload = lambda **kwargs: {
    "upload_url": f"https://upload.videodelivery.net/tus/{UID}",
    "uid": UID,
    "chunk_size": 10 * 1024 * 1024,
    "max_bytes": 30 * 1024 * 1024 * 1024,
    "expires_at": "2026-08-15T00:00:00Z",
}
token = csrf(client, f"/admin/lesson/{lesson_id}/edit")
init = client.post(
    f"/admin/lesson/{lesson_id}/stream-upload/init",
    headers={"Accept": "application/json", "X-CSRF-Token": token},
    json={"file_name": "محاضرة V57.mp4", "file_size": 600 * 1024 * 1024, "content_type": "video/mp4"},
)
assert init.status_code == 200 and init.json()["uid"] == UID
db = SessionLocal()
profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id).one()
assert profile.processing_status == "uploading" and profile.drm_mode == "signed"
db.close()

main.enforce_signed_video = lambda uid: None
main.stream_video_details = lambda uid: {
    "uid": uid,
    "creator": f"mostashar-u1-l{lesson_id}",
    "readyToStream": False,
    "duration": 3600,
    "thumbnail": f"https://customer-test.cloudflarestream.com/{uid}/thumbnails/thumbnail.jpg",
    "status": {"state": "inprogress", "pctComplete": "42"},
}
final = client.post(
    f"/admin/lesson/{lesson_id}/stream-upload/finalize",
    headers={"Accept": "application/json", "X-CSRF-Token": token},
    json={"uid": UID},
)
assert final.status_code == 200 and final.json()["state"] == "inprogress"
db = SessionLocal()
lesson = db.get(Lesson, lesson_id)
profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id).one()
assert lesson.video_url == f"https://videodelivery.net/{UID}/iframe"
assert lesson.published is False
assert profile.processing_status == "processing" and profile.duration_seconds == 3600
db.close()

# Server-side publication gate: UI manipulation must not expose a Stream video
# before Cloudflare processing is actually ready.
publish_early = client.post(
    f"/admin/lesson/{lesson_id}/update",
    data={
        "title": "محاضرة V57", "body": "",
        "video_url": f"https://videodelivery.net/{UID}/iframe",
        "order_index": "1", "published": "on", "csrf": token,
    },
    headers={"Accept": "application/json"},
)
assert publish_early.status_code == 409

main.stream_video_details = lambda uid: {
    "uid": uid,
    "readyToStream": True,
    "duration": 3600,
    "status": {"state": "ready", "pctComplete": "100"},
}
status = client.post(
    f"/admin/lesson/{lesson_id}/stream-upload/status",
    headers={"Accept": "application/json", "X-CSRF-Token": token},
    json={"uid": UID},
)
assert status.status_code == 200 and status.json()["state"] == "ready"
db = SessionLocal()
assert db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id).one().processing_status == "ready"
assert db.get(Lesson, lesson_id).published is False
db.close()

# Once ready, the same explicit publish action is allowed.
token = csrf(client, f"/admin/lesson/{lesson_id}/edit")
publish_ready = client.post(
    f"/admin/lesson/{lesson_id}/update",
    data={
        "title": "محاضرة V57", "body": "",
        "video_url": f"https://videodelivery.net/{UID}/iframe",
        "order_index": "1", "published": "on", "csrf": token,
    },
    follow_redirects=False,
)
assert publish_ready.status_code == 303
db = SessionLocal()
assert db.get(Lesson, lesson_id).published is True
db.close()

# A valid PDF sent by a browser as generic binary is normalized by extension,
# structurally validated, stored, and returned to the same lesson screen.
pdf_buffer = io.BytesIO()
pdf = canvas.Canvas(pdf_buffer)
pdf.drawString(72, 720, "Mostashar V57 attachment")
pdf.showPage()
pdf.save()
attachment = client.post(
    f"/admin/course/{course_id}/media",
    headers={"Accept": "application/json"},
    data={
        "lesson_id": lesson_id,
        "csrf": token,
        "return_to": f"/admin/lesson/{lesson_id}/edit#lesson-media",
    },
    files={"file": ("ملف المحاضرة.pdf", pdf_buffer.getvalue(), "application/octet-stream")},
)
assert attachment.status_code == 200, attachment.text
assert attachment.json()["return_to"].endswith(f"/admin/lesson/{lesson_id}/edit#lesson-media")
db = SessionLocal()
asset = db.query(MediaAsset).filter_by(lesson_id=lesson_id).one()
assert asset.mime_type == "application/pdf"
assert (media_root / asset.storage_key).is_file()
db.close()

print("V57 RESUMABLE LECTURE + ATTACHMENT UPLOAD FLOW OK")
