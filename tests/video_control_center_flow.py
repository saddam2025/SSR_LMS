import os, re, tempfile
os.environ.setdefault('ENV','development')
os.environ['DATABASE_URL']='sqlite:///' + tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import Lesson, LessonVideoProfile, User
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()
db=SessionLocal(); lesson=db.query(Lesson).first(); assert lesson; lesson_id=lesson.id; db.close()

def login(c,email,password):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=False)
    assert r.status_code==303, r.text

c=TestClient(app); login(c,'admin@ragab-seddik.local','ChangeMe123!')
r=c.get(f'/admin/lesson/{lesson_id}/edit'); assert r.status_code==200, r.text
assert 'VIDEO CONTROL CENTER' in r.text and 'إعدادات الفيديو والبث' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/lesson/{lesson_id}/video-profile',data={
    'provider':'mux','stream_type':'hls','drm_mode':'signed','processing_status':'ready',
    'thumbnail_url':'https://images.example.com/lesson.jpg','duration_minutes':'12','duration_seconds':'34','csrf':csrf
},follow_redirects=False)
assert r.status_code==303, r.text
db=SessionLocal(); p=db.query(LessonVideoProfile).filter_by(lesson_id=lesson_id).first(); assert p
assert (p.provider,p.stream_type,p.drm_mode,p.processing_status,p.duration_seconds)==('mux','hls','signed','ready',754)
db.close()
print('VIDEO CONTROL CENTER FLOW OK')
