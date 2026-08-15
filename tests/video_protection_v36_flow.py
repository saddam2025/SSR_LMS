import os, re
os.environ.setdefault('DATABASE_URL','sqlite:///./video_protection_v36_test.db')
os.environ.pop('ENV', None)
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import User, Lesson, Enrollment

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed()
db=SessionLocal()
student=db.query(User).filter_by(role='student').first()
lesson=db.query(Lesson).filter_by(published=True).order_by(Lesson.id).first()
assert student and lesson
if not db.query(Enrollment).filter_by(user_id=student.id, course_id=lesson.course_id).first():
    db.add(Enrollment(user_id=student.id, course_id=lesson.course_id, active=True))
lesson.video_url='https://video.example.test/private/sample.mp4'
db.commit(); lesson_id=lesson.id; student_name=student.name; db.close()

c=TestClient(app)
r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/login',data={'email':'student@ragab-seddik.local','password':'Student123!','csrf':csrf},follow_redirects=False)
assert r.status_code in (302,303)
r=c.get(f'/lesson/{lesson_id}'); assert r.status_code==200, r.text
# The user-identifying watermark is generated server-side and appears in the video frame.
assert student_name in r.text
assert 'SESSION ' in r.text
assert 'data-video-watermark' in r.text
# Direct raw MP4 origin must not be present in the rendered video src.
assert 'src="https://video.example.test/private/sample.mp4"' not in r.text
m=re.search(r'src="(/protected/video/%d\?token=[^"]+)"' % lesson_id, r.text)
assert m, r.text
# Session-bound endpoint rejects tampered/invalid tokens before any upstream fetch.
r=c.get(f'/protected/video/{lesson_id}?token=bad-token')
assert r.status_code==403
print('VIDEO PROTECTION V36 FLOW OK')
