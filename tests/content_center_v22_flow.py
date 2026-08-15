import os,tempfile,re
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v22-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,Lesson,Quiz,Homework,ContentUnit,LessonUnitAssignment,QuizUnitAssignment,HomeworkUnitAssignment
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
c=Course(title='English First Secondary',grade='الصف الأول الثانوي',published=True)
db.add_all([admin,c]); db.commit(); db.refresh(c)
l=Lesson(course_id=c.id,title='Lesson One',published=False,order_index=1)
q=Quiz(course_id=c.id,title='Quiz One',published=False,time_limit_minutes=20,max_attempts=2)
h=Homework(course_id=c.id,title='Homework One',published=True)
db.add_all([l,q,h]); db.commit(); ids=(c.id,l.id,q.id,h.id); db.close()
client=TestClient(app)
r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=client.get('/teacher/content'); assert r.status_code==200 and 'مركز محتوى مستر رجب صديق' in r.text and 'الصف الأول الثانوي' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
cid,lid,qid,hid=ids
r=client.post('/teacher/content/unit',data={'course_id':cid,'name':'Unit 1','description':'Core unit','order_index':1,'csrf':csrf},follow_redirects=False); assert r.status_code==303

db=SessionLocal(); unit=db.query(ContentUnit).filter_by(course_id=cid,name='Unit 1').one(); uid=unit.id; db.close()
for typ,i in [('lesson',lid),('quiz',qid),('homework',hid)]:
    r=client.post('/teacher/content/assign',data={'content_type':typ,'content_id':i,'unit_id':uid,'csrf':csrf},follow_redirects=False); assert r.status_code==303,(typ,r.status_code,r.text[:200])
db=SessionLocal(); assert db.query(LessonUnitAssignment).filter_by(lesson_id=lid,unit_id=uid).first(); assert db.query(QuizUnitAssignment).filter_by(quiz_id=qid,unit_id=uid).first(); assert db.query(HomeworkUnitAssignment).filter_by(homework_id=hid,unit_id=uid).first(); db.close()
r=client.get('/teacher/content'); assert 'Unit 1' in r.text and 'Lesson One' in r.text and 'Quiz One' in r.text and 'Homework One' in r.text
r=client.post(f'/teacher/content/unit/{uid}/toggle',data={'csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); assert db.get(ContentUnit,uid).published is False; db.close()
print('CONTENT CENTER V22 FLOW OK')
