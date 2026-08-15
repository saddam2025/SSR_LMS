import os, tempfile
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ.setdefault('APP_SECRET','v53-auth-contract-secret')
os.environ.setdefault('REQUIRE_STAFF_MFA','false')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal(); db.add_all([
 User(name='Student V53',email='student53@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True),
 User(name='Admin V53',email='admin53@example.com',password_hash=hash_password('AdminPass12345'),role='admin',is_active=True,mfa_enabled=True),
]); db.commit(); db.close()
c=TestClient(app)
# Browser unauthenticated access recovers through login, never a raw 401 page.
r=c.get('/dashboard',follow_redirects=False); assert r.status_code==303 and r.headers['location'].startswith('/login'), r.status_code
# API keeps standards-correct 401 JSON.
r=c.get('/api/v1/courses'); assert r.status_code==401 and r.json()['error']['status']==401
# Student login then accidental admin URL is safely redirected, not exposed as a raw 403 page.
csrf=c.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0]
r=c.post('/login',data={'email':'student53@example.com','password':'StudentPass12345','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=c.get('/admin',follow_redirects=False); assert r.status_code==303 and r.headers['location'].startswith('/dashboard'), (r.status_code,r.headers.get('location'))
print('AUTH HTTP CONTRACT V53 OK')
