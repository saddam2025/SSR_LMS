import os
import re
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./video_watermark_v39_test.db")
os.environ.pop("ENV", None)

from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import main as main_module
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Enrollment, Lesson, User
from app.seed import run as seed

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
seed()
db = SessionLocal()
student = db.query(User).filter_by(role="student").first()
lesson = db.query(Lesson).filter_by(published=True).order_by(Lesson.id).first()
assert student and lesson
if not db.query(Enrollment).filter_by(user_id=student.id, course_id=lesson.course_id).first():
    db.add(Enrollment(user_id=student.id, course_id=lesson.course_id, active=True))
lesson.video_url = "https://video.example.test/private/sample.mp4"
db.commit()
lesson_id = lesson.id
student_name = student.name
db.close()

client = TestClient(app)
response = client.get("/login")
csrf = re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)
response = client.post("/login", data={"email": "student@ragab-seddik.local", "password": "Student123!", "csrf": csrf}, follow_redirects=False)
assert response.status_code in (302, 303)
response = client.get(f"/lesson/{lesson_id}")
assert response.status_code == 200
assert student_name in response.text
assert 'data-watermark-integrity="persistent-v40"' in response.text
assert "'unsafe-inline'" not in response.headers["content-security-policy"].split("script-src", 1)[1].split(";", 1)[0]
match = re.search(r'src="(/protected/video/%d\?token=[^"]+)"' % lesson_id, response.text)
assert match
video_path = match.group(1).replace("&amp;", "&")
assert client.get(f"/protected/video/{lesson_id}?token=bad-token").status_code == 403
assert client.head(video_path).status_code == 405
assert client.get(video_path, headers={"Range": "bytes=invalid"}).status_code == 416

script = (Path(__file__).resolve().parents[1] / "app/static/protected-content.js").read_text(encoding="utf-8")
assert "localStorage" in script
assert "MutationObserver" in script
assert "ensureProtection" in script
assert "videoWatermark.parentNode !== videoZone" in script

saved_production = main_module.IS_PRODUCTION
saved_allowlist = os.environ.get("VIDEO_ALLOWED_HOSTS")
saved_direct = os.environ.get("ALLOW_DIRECT_VIDEO_PROXY")
try:
    main_module.IS_PRODUCTION = True
    os.environ["VIDEO_ALLOWED_HOSTS"] = "video.example.test"
    os.environ["ALLOW_DIRECT_VIDEO_PROXY"] = "false"
    try:
        main_module.validated_video_url("https://video.example.test/private/sample.mp4")
        raise AssertionError("Production accepted a raw MP4 URL")
    except HTTPException as exc:
        assert exc.status_code == 400
finally:
    main_module.IS_PRODUCTION = saved_production
    if saved_allowlist is None:
        os.environ.pop("VIDEO_ALLOWED_HOSTS", None)
    else:
        os.environ["VIDEO_ALLOWED_HOSTS"] = saved_allowlist
    if saved_direct is None:
        os.environ.pop("ALLOW_DIRECT_VIDEO_PROXY", None)
    else:
        os.environ["ALLOW_DIRECT_VIDEO_PROXY"] = saved_direct

print("VIDEO WATERMARK V39 FLOW OK")
