import os, re
os.environ.setdefault('DATABASE_URL','sqlite:///./protected_assets_v37_test.db')
os.environ.pop('ENV', None)
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import User, Lesson, MediaAsset, LessonProgress
from app.watermark import trace_text

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed()
db=SessionLocal()
student=db.query(User).filter_by(email='student@ragab-seddik.local').first()
lessons=db.query(Lesson).filter_by(course_id=1,published=True).order_by(Lesson.order_index).all()
assert student and len(lessons)>=2
first,second=lessons[0],lessons[1]
asset=MediaAsset(lesson_id=second.id,owner_id=1,original_name='locked.pdf',storage_key='does-not-exist.pdf',mime_type='application/pdf',size_bytes=10,provider='local')
db.add(asset); db.commit(); aid=asset.id
# File/image traces now include the student's visible name, not only an ID/email.
assert student.name in trace_text(student.id, student.email, student.name)
db.close()

c=TestClient(app,headers={'user-agent':'ProtectedAssetsV37/1','accept-language':'ar-EG'})
r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/login',data={'email':'student@ragab-seddik.local','password':'Student123!','csrf':csrf},follow_redirects=False)
assert r.status_code in (302,303)
# Asset of lesson 2 is blocked until lesson 1 is completed.
r=c.get(f'/protected/media/{aid}'); assert r.status_code==403, r.status_code
# Once the prerequisite is completed, authorization passes; the dummy storage
# object then correctly fails as missing (404), proving access control changed first.
db=SessionLocal(); db.add(LessonProgress(user_id=student.id,lesson_id=first.id,completed=True,watched_seconds=60)); db.commit(); db.close()
r=c.get(f'/protected/media/{aid}'); assert r.status_code==404, r.status_code
print('PROTECTED ASSETS V37 FLOW OK')
