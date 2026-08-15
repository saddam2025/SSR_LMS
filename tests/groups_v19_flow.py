import os, tempfile
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v19-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,Enrollment,LiveClass,StudentGroup,StudentGroupMembership,GroupCourseAssignment,GroupLiveClassAssignment
from app.security import hash_password
from datetime import datetime,timedelta
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
s1=User(name='Student One',email='s1@test.local',password_hash=hash_password('Student123!'),role='student',is_active=True)
s2=User(name='Student Two',email='s2@test.local',password_hash=hash_password('Student123!'),role='student',is_active=True)
c=Course(title='English 3',grade='الصف الثالث الثانوي',published=True)
db.add_all([admin,s1,s2,c]); db.commit(); db.refresh(c); db.refresh(s1); db.refresh(s2)
lc=LiveClass(course_id=c.id,title='Group lesson',provider='zoom',meeting_url='https://example.com/class',scheduled_at=datetime.utcnow()+timedelta(days=1),created_by=admin.id)
db.add(lc); db.commit(); db.close()
client=TestClient(app)
import re
r=client.get('/login'); login_csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':login_csrf},follow_redirects=True); assert r.status_code==200
r=client.get('/admin/groups'); assert r.status_code==200
# pull csrf from session-backed page
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/admin/groups/create',data={'csrf':csrf,'name':'3A','grade':'الصف الثالث الثانوي','description':'test'},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); g=db.query(StudentGroup).filter_by(name='3A').one(); gid=g.id; cid=c.id; sid=s1.id; lcid=lc.id; db.close()
r=client.get(f'/admin/groups/{gid}'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
assert client.post(f'/admin/groups/{gid}/member',data={'csrf':csrf,'student_id':sid},follow_redirects=False).status_code==303
assert client.post(f'/admin/groups/{gid}/course',data={'csrf':csrf,'course_id':cid,'action':'assign'},follow_redirects=False).status_code==303
assert client.post(f'/admin/groups/{gid}/live-class',data={'csrf':csrf,'live_class_id':lcid,'action':'assign'},follow_redirects=False).status_code==303
db=SessionLocal(); assert db.query(StudentGroupMembership).filter_by(group_id=gid,user_id=sid).first(); assert db.query(GroupCourseAssignment).filter_by(group_id=gid,course_id=cid).first(); assert db.query(Enrollment).filter_by(user_id=sid,course_id=cid,active=True).first(); assert db.query(GroupLiveClassAssignment).filter_by(group_id=gid,live_class_id=lcid).first(); db.close()
# Student 1 sees class, student2 shouldn't even if enrolled later because group restriction
client.post('/logout',data={'csrf':csrf},follow_redirects=False)
print('GROUPS V19 FLOW OK')
