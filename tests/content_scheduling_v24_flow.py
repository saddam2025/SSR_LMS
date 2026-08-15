import os,tempfile,re
from datetime import datetime,timedelta
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v24-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,Lesson,Quiz,Homework,ContentUnit,LessonUnitAssignment,QuizUnitAssignment,HomeworkUnitAssignment,Enrollment,ContentSchedule
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
student=User(name='Student',email='student@test.local',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
c=Course(title='English Third Secondary',grade='الصف الثالث الثانوي',published=True)
db.add_all([admin,student,c]); db.commit(); db.refresh(c); db.refresh(student)
u=ContentUnit(course_id=c.id,name='Unit 1',published=True,order_index=1); db.add(u); db.flush()
l=Lesson(course_id=c.id,title='Scheduled Lesson',body='body',published=True,order_index=1); db.add(l); db.flush(); db.add(LessonUnitAssignment(lesson_id=l.id,unit_id=u.id))
q=Quiz(course_id=c.id,title='Scheduled Quiz',published=True,time_limit_minutes=20,max_attempts=1); db.add(q); db.flush(); db.add(QuizUnitAssignment(quiz_id=q.id,unit_id=u.id))
h=Homework(course_id=c.id,title='Scheduled Homework',published=True); db.add(h); db.flush(); db.add(HomeworkUnitAssignment(homework_id=h.id,unit_id=u.id))
db.add(Enrollment(user_id=student.id,course_id=c.id,active=True)); db.commit(); ids=(c.id,u.id,l.id,q.id,h.id); db.close()

# Admin schedules the unit for the future.
admin_client=TestClient(app)
r=admin_client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=admin_client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=admin_client.get('/teacher/content'); assert r.status_code==200 and 'مجدول لاحقًا' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
cid,uid,lid,qid,hid=ids
future=(datetime.utcnow()+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')
r=admin_client.post('/teacher/content/schedule',data={'content_type':'unit','content_id':uid,'starts_at':future,'ends_at':'','enabled':'1','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=admin_client.get('/teacher/content'); assert '⏳ مجدول' in r.text or 'مجدول' in r.text

# Student must not see or open children while the parent unit is not active.
student_client=TestClient(app)
r=student_client.get('/login'); csrf_s=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=student_client.post('/login',data={'email':'student@test.local','password':'StudentPass12345','csrf':csrf_s},follow_redirects=True); assert r.status_code==200
r=student_client.get(f'/course/{cid}'); assert r.status_code==200 and 'Scheduled Lesson' not in r.text and 'Scheduled Quiz' not in r.text and 'Scheduled Homework' not in r.text
assert student_client.get(f'/lesson/{lid}').status_code==404
assert student_client.get(f'/quiz/{qid}').status_code==404
assert student_client.get(f'/homework/{hid}').status_code==403

# Make unit active now, then expire lesson only.
db=SessionLocal(); us=db.query(ContentSchedule).filter_by(content_type='unit',content_id=uid).one(); us.starts_at=datetime.utcnow()-timedelta(hours=1); db.add(ContentSchedule(content_type='lesson',content_id=lid,starts_at=datetime.utcnow()-timedelta(days=2),ends_at=datetime.utcnow()-timedelta(hours=1),enabled=True)); db.commit(); db.close()
r=student_client.get(f'/course/{cid}'); assert 'Scheduled Lesson' not in r.text and 'Scheduled Quiz' in r.text and 'Scheduled Homework' in r.text
assert student_client.get(f'/lesson/{lid}').status_code==404

# Disable lesson schedule; manual publish state takes over and content is visible again.
db=SessionLocal(); ls=db.query(ContentSchedule).filter_by(content_type='lesson',content_id=lid).one(); ls.enabled=False; db.commit(); db.close()
r=student_client.get(f'/course/{cid}'); assert 'Scheduled Lesson' in r.text
assert student_client.get(f'/lesson/{lid}').status_code==200
print('CONTENT SCHEDULING V24 FLOW OK')
