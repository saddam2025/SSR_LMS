import os, re, tempfile
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='login-safety-v96-test-secret-12345678901234567890'
os.environ['ENV']='test'
os.environ['REQUIRE_STAFF_MFA']='true'
os.environ['SEPARATED_FRONTEND_ENABLED']='false'
os.environ['FRONTEND_PRIMARY_ORIGIN']='https://student.ragab-seddik.com'
os.environ['FRONTEND_ORIGINS']='https://student.ragab-seddik.com'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,StudentProfile
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='owner@test.local',password_hash=hash_password('AdminPass12345'),role='admin',is_active=True,mfa_enabled=False)
student=User(name='Student',email='student@test.local',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)
parent=User(name='Parent',email='parent@test.local',password_hash=hash_password('ParentPass12345'),role='parent',is_active=True)
db.add_all([admin,student,parent]); db.flush(); db.add(StudentProfile(user_id=student.id,phone='01000000999',grade='الصف الأول الثانوي')); db.commit(); db.close()

def login(email,password):
    c=TestClient(app); r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    return c,c.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=False)

c,r=login('owner@test.local','AdminPass12345'); assert r.status_code==303 and r.headers['location']=='/account/security?required=1'; assert c.get(r.headers['location']).status_code==200
c,r=login('student@test.local','StudentPass12345'); assert r.status_code==303 and r.headers['location']=='/dashboard'; assert c.get('/dashboard').status_code==200
c,r=login('01000000999','StudentPass12345'); assert r.status_code==303 and r.headers['location']=='/dashboard'
c,r=login('parent@test.local','ParentPass12345'); assert r.status_code==303 and r.headers['location']=='/parent'; assert c.get('/parent').status_code==200
print('V96 LOGIN REDIRECT SAFETY: PASS')
