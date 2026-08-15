import os, re
os.environ.setdefault('DATABASE_URL','sqlite:///./video_feature_test.db')
os.environ.pop('ENV',None)
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import User, Lesson, Enrollment, LessonCheckpoint, LessonFlashcard, OfflineLessonPolicy, CheckpointAttempt, StudyAssistantLog

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed()
db=SessionLocal()
student=db.query(User).filter_by(role='student').first()
lesson=db.query(Lesson).filter_by(published=True).order_by(Lesson.id).first()
assert student and lesson
# Ensure access regardless of seed enrollment layout.
if not db.query(Enrollment).filter_by(user_id=student.id, course_id=lesson.course_id).first():
    db.add(Enrollment(user_id=student.id, course_id=lesson.course_id, active=True))
cp=LessonCheckpoint(lesson_id=lesson.id,timestamp_seconds=15,question='Choose the correct answer',option_a='A1',option_b='B1',option_c='C1',option_d='D1',correct='B',explanation='B is correct because it matches the lesson explanation.',published=True)
fc=LessonFlashcard(lesson_id=lesson.id,front='Key word',back='Key meaning from the lesson',published=True)
pol=OfflineLessonPolicy(lesson_id=lesson.id,enabled=True,provider_asset_id='asset-demo',max_offline_days=7,max_devices=1)
db.add_all([cp,fc,pol]); db.commit(); cp_id=cp.id; lesson_id=lesson.id; db.close()

def login(client,email,password):
    r=client.get('/login'); token=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':token},follow_redirects=False)
    assert r.status_code in (302,303), r.text

c=TestClient(app); login(c,'student@ragab-seddik.local','Student123!')
r=c.get(f'/lesson/{lesson_id}'); assert r.status_code==200, r.text
assert 'مساعدك الذكي للمذاكرة' in r.text and 'Flash Cards' in r.text and 'اختبر نفسك على كل جزء' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/lesson/{lesson_id}/checkpoint/{cp_id}',data={'answer':'B','csrf':csrf},follow_redirects=True); assert r.status_code==200
assert 'أحسنت — الإجابة صحيحة' in r.text
r=c.post(f'/lesson/{lesson_id}/assistant',data={'question':'اشرح لي Key word','csrf':csrf}); assert r.status_code==200
assert 'الشرح التالي مبني فقط على محتوى الدرس الذي أضافه مستر رجب صديق' in r.text
r=c.get(f'/api/mobile/offline/lesson/{lesson_id}/capability'); assert r.status_code==200 and r.json()['inside_app_only'] is True

db=SessionLocal(); assert db.query(CheckpointAttempt).count()==1; assert db.query(StudyAssistantLog).count()==1; db.close()
print('VIDEO FEATURE FLOW OK')
