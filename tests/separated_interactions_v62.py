import os, tempfile, sys
from pathlib import Path
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v62-separated-interactions-secret-'+'x'*80
os.environ['SESSION_SECRET']='v62-session-secret-'+'y'*80
os.environ['REQUIRE_STAFF_MFA']='false'
os.environ['FRONTEND_ORIGINS']='https://www.ragab-seddik.com'
os.environ['FRONTEND_PRIMARY_ORIGIN']='https://www.ragab-seddik.com'
os.environ['SEPARATED_FRONTEND_ENABLED']='true'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User, Course, Lesson, Enrollment, LessonCheckpoint, PointLedger, StudyAssistantLog, DiscussionPost
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
student=User(name='Student V62',email='student62@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
course=Course(title='V62 Course',grade='الصف الثاني الثانوي عام',published=True)
db.add_all([student,course]); db.flush()
lesson=Lesson(course_id=course.id,title='Lesson V62',body='Photosynthesis converts light energy into chemical energy in plants. Chlorophyll absorbs light.',published=True,order_index=1)
db.add(lesson); db.flush(); db.add(Enrollment(user_id=student.id,course_id=course.id,active=True))
cp=LessonCheckpoint(lesson_id=lesson.id,timestamp_seconds=30,question='What absorbs light?',option_a='Chlorophyll',option_b='Water',option_c='Soil',option_d='Air',correct='A',explanation='Chlorophyll absorbs light.',published=True)
db.add(cp); db.commit(); lesson_id=lesson.id; cp_id=cp.id; student_id=student.id; db.close()

c=TestClient(app)
csrf=c.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0]
r=c.post('/login',data={'email':'student62@example.com','password':'StudentPass12345','csrf':csrf},follow_redirects=False)
assert r.status_code==303, r.text
session=c.get('/api/v1/session'); assert session.status_code==200, session.text
api_csrf=session.json()['data']['csrf']
# CSRF is required for separated writes.
r=c.post(f'/api/v1/lessons/{lesson_id}/checkpoints/{cp_id}/answer',json={'answer':'A'})
assert r.status_code==403, r.text
# Checkpoint can be answered and reveals correction only after submission.
r=c.post(f'/api/v1/lessons/{lesson_id}/checkpoints/{cp_id}/answer',json={'answer':'A'},headers={'X-CSRF-Token':api_csrf})
assert r.status_code==200, r.text
assert r.json()['data']['is_correct'] is True and r.json()['data']['correct']=='A'
# Re-answering must not award points twice.
r=c.post(f'/api/v1/lessons/{lesson_id}/checkpoints/{cp_id}/answer',json={'answer':'B'},headers={'X-CSRF-Token':api_csrf})
assert r.status_code==200 and r.json()['data']['is_correct'] is False
db=SessionLocal(); assert db.query(PointLedger).filter_by(user_id=student_id,ref_type='checkpoint',ref_id=cp_id).count()==1; db.close()
# Assistant is content-grounded and logged server-side.
r=c.post(f'/api/v1/lessons/{lesson_id}/assistant',json={'question':'What does chlorophyll absorb?','mode':'explain'},headers={'X-CSRF-Token':api_csrf})
assert r.status_code==200, r.text
payload=r.json()['data']; assert payload['grounded_only'] is True and 'Chlorophyll' in payload['answer']
db=SessionLocal(); assert db.query(StudyAssistantLog).filter_by(user_id=student_id,lesson_id=lesson_id).count()==1; db.close()
# Discussion create/list works with server-side identity, not a client supplied author.
r=c.post(f'/api/v1/lessons/{lesson_id}/discussion',json={'body':'سؤال عن هذا الجزء'},headers={'X-CSRF-Token':api_csrf})
assert r.status_code==200, r.text; assert r.json()['data']['author']=='Student V62'
r=c.get(f'/api/v1/lessons/{lesson_id}/discussion'); assert r.status_code==200 and len(r.json()['data'])==1
assert r.json()['data'][0]['body']=='سؤال عن هذا الجزء'
# Static frontend contract: interactions use API and render content through textContent helpers.
js=Path('frontend/assets/app.js').read_text(); html=Path('frontend/student/lesson.html').read_text(); router=Path('app/api_v1.py').read_text()
for needle in ['/checkpoints/${cp.id}/answer','/assistant','/discussion']:
    assert needle in js
assert 'assistant-form' in html and 'discussion-form' in html
assert 'interactions_router' in router
print('V62 SEPARATED LESSON INTERACTIONS CONTRACT OK')
