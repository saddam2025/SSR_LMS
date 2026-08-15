import os,tempfile,re
from datetime import datetime,timedelta
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v25-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,Lesson,Enrollment,LessonProgress,LessonDripRule,LessonAccessOverride
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
student=User(name='Student',email='student@test.local',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
c=Course(title='V25 Course',grade='الصف الثالث الثانوي',published=True)
db.add_all([admin,student,c]); db.commit(); db.refresh(student); db.refresh(c)
l1=Lesson(course_id=c.id,title='Lesson 1',body='one',published=True,order_index=1)
l2=Lesson(course_id=c.id,title='Lesson 2',body='two',published=True,order_index=2)
l3=Lesson(course_id=c.id,title='Lesson 3',body='three',published=True,order_index=3)
db.add_all([l1,l2,l3]); db.flush()
e=Enrollment(user_id=student.id,course_id=c.id,active=True,created_at=datetime.utcnow())
db.add(e); db.add(LessonDripRule(lesson_id=l3.id,mode='days',delay_days=7,enabled=True)); db.commit()
ids=(c.id,l1.id,l2.id,l3.id,student.id); db.close()

def login(email,password):
    cl=TestClient(app); r=cl.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=cl.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=True); assert r.status_code==200
    return cl
student_client=login('student@test.local','StudentPass12345')
cid,l1id,l2id,l3id,sid=ids
# Default behavior remains previous-lesson gating.
r=student_client.get(f'/course/{cid}'); assert r.status_code==200 and 'Lesson 1' in r.text and 'أكمل الدرس السابق أولًا' in r.text
assert student_client.get(f'/lesson/{l1id}').status_code==200
assert student_client.get(f'/lesson/{l2id}').status_code==403
# Mark lesson 1 complete; lesson 2 opens.
db=SessionLocal(); db.add(LessonProgress(user_id=sid,lesson_id=l1id,completed=True,watched_seconds=120)); db.commit(); db.close()
assert student_client.get(f'/lesson/{l2id}').status_code==200
# Lesson 3 is days-based and still locked.
r=student_client.get(f'/course/{cid}'); assert 'يفتح بعد 7 يوم من الاشتراك' in r.text
assert student_client.get(f'/lesson/{l3id}').status_code==403
# Admin opens lesson 3 manually for this student.
admin_client=login('admin@test.local','AdminPass12345')
r=admin_client.get(f'/admin/lesson/{l3id}/edit'); assert r.status_code==200 and 'DRIP CONTENT V25' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=admin_client.post(f'/admin/lesson/{l3id}/access-override',data={'student_id':sid,'action':'unlock','expires_at':'','note':'Special access','csrf':csrf},follow_redirects=False); assert r.status_code==303
assert student_client.get(f'/lesson/{l3id}').status_code==200
# Manual lock supersedes an open rule.
r=admin_client.post(f'/admin/lesson/{l2id}/drip-rule',data={'mode':'open','delay_days':0,'enabled':'on','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=admin_client.post(f'/admin/lesson/{l2id}/access-override',data={'student_id':sid,'action':'lock','expires_at':'','note':'Pause','csrf':csrf},follow_redirects=False); assert r.status_code==303
assert student_client.get(f'/lesson/{l2id}').status_code==403
# Clearing override reveals open rule again.
r=admin_client.post(f'/admin/lesson/{l2id}/access-override',data={'student_id':sid,'action':'clear','expires_at':'','note':'','csrf':csrf},follow_redirects=False); assert r.status_code==303
assert student_client.get(f'/lesson/{l2id}').status_code==200
# Advance enrollment age so day-based lesson naturally opens after clearing manual override.
db=SessionLocal(); e=db.query(Enrollment).filter_by(user_id=sid,course_id=cid).one(); e.created_at=datetime.utcnow()-timedelta(days=8); ov=db.query(LessonAccessOverride).filter_by(user_id=sid,lesson_id=l3id).one(); db.delete(ov); db.commit(); db.close()
assert student_client.get(f'/lesson/{l3id}').status_code==200
print('DRIP CONTENT V25 FLOW OK')
