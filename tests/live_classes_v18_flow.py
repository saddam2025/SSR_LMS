import os
os.environ.setdefault('ENV','test'); os.environ.setdefault('APP_SECRET','test-secret-change-this')
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal, Base, engine
from app.models import User, Course, Enrollment, LiveClass, LiveClassAttendance, Notification
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
for m in [LiveClassAttendance,LiveClass,Enrollment,Notification]: db.query(m).delete()
db.query(Course).delete(); db.query(User).delete(); db.commit()
admin=User(name='Admin',email='adminv18@test.com',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
st=User(name='Student',email='studentv18@test.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
db.add_all([admin,st]); db.flush(); c=Course(title='English Live',grade='الصف الثالث الثانوي',published=True,teacher_id=admin.id); db.add(c); db.flush(); db.add(Enrollment(user_id=st.id,course_id=c.id,active=True)); db.commit(); db.close()
cl=TestClient(app)
r=cl.get('/login'); import re; csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=cl.post('/login',data={'email':'adminv18@test.com','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=cl.get('/admin/live-classes'); assert r.status_code==200 and 'الحصص المباشرة' in r.text
import re
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=cl.post('/admin/live-classes/create',data={'csrf':csrf,'course_id':str(c.id),'title':'مراجعة مباشرة','provider':'zoom','meeting_url':'https://zoom.us/j/123','scheduled_at':'2026-08-13T18:00','duration_minutes':'60','notes':'مراجعة'},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); live=db.query(LiveClass).one(); assert db.query(Notification).filter_by(user_id=st.id).count()>=1; db.close()
cl.post('/logout',data={'csrf':csrf},follow_redirects=False)
r=cl.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=cl.post('/login',data={'email':'studentv18@test.com','password':'StudentPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=cl.get('/schedule'); assert r.status_code==200 and 'مراجعة مباشرة' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=cl.post(f'/live-class/{live.id}/join',data={'csrf':csrf},follow_redirects=False); assert r.status_code==303 and r.headers['location'].startswith('https://zoom.us')
db=SessionLocal(); assert db.query(LiveClassAttendance).filter_by(live_class_id=live.id,user_id=st.id,status='present').first(); db.close()
print('LIVE CLASSES V18 FLOW OK')
