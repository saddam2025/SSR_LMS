import os, re
os.environ.setdefault('DATABASE_URL','sqlite:///./account_sharing_v37_test.db')
os.environ.pop('ENV', None)
os.environ['MAX_DEVICES_PER_USER']='2'
os.environ['STUDENT_SINGLE_SESSION']='true'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import User, ActiveSession, Device

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed()

def login(client):
    r=client.get('/login')
    csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    return client.post('/login',data={'email':'student@ragab-seddik.local','password':'Student123!','csrf':csrf},follow_redirects=False)

# Two clients deliberately use the same UA. The persistent random device token
# must still make them two distinct devices.
c1=TestClient(app, headers={'user-agent':'SameBrowser/1.0','accept-language':'ar-EG'})
c2=TestClient(app, headers={'user-agent':'SameBrowser/1.0','accept-language':'ar-EG'})
c3=TestClient(app, headers={'user-agent':'SameBrowser/1.0','accept-language':'ar-EG'})
assert login(c1).status_code in (302,303)
assert c1.get('/dashboard').status_code==200
assert login(c2).status_code in (302,303)
# New login revokes the previous student session.
r=c1.get('/dashboard', follow_redirects=False); assert r.status_code==303 and r.headers['location'].startswith('/login')
assert c2.get('/dashboard').status_code==200

db=SessionLocal(); student=db.query(User).filter_by(role='student').first()
assert db.query(ActiveSession).filter(ActiveSession.user_id==student.id,ActiveSession.revoked_at.is_(None)).count()==1
assert db.query(Device).filter(Device.user_id==student.id,Device.blocked==False).count()==2
db.close()
# A third physical/browser device is refused because the account already owns two.
r=login(c3); assert r.status_code==403, r.status_code
print('ACCOUNT SHARING V37 FLOW OK')
