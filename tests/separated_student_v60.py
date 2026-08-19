import os, tempfile
from datetime import datetime, timedelta
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v60-separated-student-secret'
os.environ['REQUIRE_STAFF_MFA']='false'
os.environ['FRONTEND_ORIGINS']='https://www.ragab-seddik.com'
os.environ['FRONTEND_PRIMARY_ORIGIN']='https://www.ragab-seddik.com'
os.environ['SEPARATED_FRONTEND_ENABLED']='true'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User, Course, Lesson, Enrollment, LessonDripRule, LessonProgress
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
student=User(name='Student V60',email='student60@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
parent=User(name='Parent V60',email='parent60@example.com',password_hash=hash_password('ParentPass12345'),role='parent',is_active=True)
course=Course(title='V60 Course',grade='الصف الثاني الثانوي عام',published=True)
db.add_all([student,parent,course]); db.flush()
lesson1=Lesson(course_id=course.id,title='Lesson 1',published=True,order_index=1)
lesson2=Lesson(course_id=course.id,title='Lesson 2',published=True,order_index=2)
db.add_all([lesson1,lesson2]); db.flush()
db.add(Enrollment(user_id=student.id,course_id=course.id,active=True))
db.add(LessonDripRule(lesson_id=lesson2.id,mode='previous',enabled=True))
db.commit(); ids=(course.id,lesson1.id,lesson2.id); db.close()
course_id, lesson1_id, lesson2_id = ids
c=TestClient(app)
csrf=c.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0]
r=c.post('/login',data={'email':'student60@example.com','password':'StudentPass12345','csrf':csrf},follow_redirects=False)
assert r.status_code==303 and r.headers['location']=='https://www.ragab-seddik.com/student/'
r=c.get('/api/v1/courses'); assert r.status_code==200, r.text
assert [x['id'] for x in r.json()['data']]==[course_id]
r=c.get(f'/api/v1/courses/{course_id}/lessons'); assert r.status_code==200, r.text
lessons=r.json()['data']; assert len(lessons)==2
assert lessons[0]['unlocked'] is True and lessons[0]['launch_url']==f'/lesson/{lesson1_id}'
assert lessons[1]['unlocked'] is False and lessons[1]['launch_url'] is None
# API cannot bypass drip lock.
r=c.get(f'/api/v1/lessons/{lesson2_id}'); assert r.status_code==403
# Complete the previous lesson in DB and access is unlocked through the same shared service.
db=SessionLocal(); db.add(LessonProgress(user_id=student.id,lesson_id=lesson1_id,completed=True)); db.commit(); db.close()
r=c.get(f'/api/v1/courses/{course_id}/lessons'); assert r.status_code==200
assert r.json()['data'][1]['unlocked'] is True
r=c.get(f'/api/v1/lessons/{lesson2_id}'); assert r.status_code==200 and r.json()['data']['launch_url']==f'/lesson/{lesson2_id}'
# Frontend route never leaks a raw video source through the API contract.
assert 'video_url' not in r.json()['data']
# Parent session is authenticated but cannot consume student endpoints.
c2=TestClient(app); csrf=c2.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0]
r=c2.post('/login',data={'email':'parent60@example.com','password':'ParentPass12345','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=c2.get('/api/v1/courses'); assert r.status_code==403
print('V60 SEPARATED STUDENT FRONTEND CONTRACT OK')
