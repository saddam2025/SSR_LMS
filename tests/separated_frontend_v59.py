import os, tempfile
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v59-separated-frontend-secret'
os.environ['REQUIRE_STAFF_MFA']='false'
os.environ['FRONTEND_ORIGINS']='https://www.ragab-seddik.com'
os.environ['FRONTEND_PRIMARY_ORIGIN']='https://www.ragab-seddik.com'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal(); db.add(User(name='Student V59',email='student59@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)); db.commit(); db.close()
c=TestClient(app)
# CORS is allowlisted and credential-aware.
r=c.options('/api/v1/session',headers={'Origin':'https://www.ragab-seddik.com','Access-Control-Request-Method':'GET'})
assert r.status_code==200
assert r.headers.get('access-control-allow-origin')=='https://www.ragab-seddik.com'
assert r.headers.get('access-control-allow-credentials')=='true'
# Login remains backend-owned and redirects student to separated frontend when configured.
csrf=c.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0]
r=c.post('/login',data={'email':'student59@example.com','password':'StudentPass12345','csrf':csrf},follow_redirects=False)
assert r.status_code==303 and r.headers['location']=='https://www.ragab-seddik.com/student/'
# Frontend bootstraps from the API session without exposing the session token.
r=c.get('/api/v1/session',headers={'Origin':'https://www.ragab-seddik.com'})
assert r.status_code==200, r.text
data=r.json()['data']; assert data['name']=='Student V59' and data['role']=='student' and data['csrf']
# Logout rejects a missing/invalid CSRF token, then succeeds with the session CSRF.
r=c.post('/api/v1/logout',headers={'Origin':'https://www.ragab-seddik.com','X-CSRF-Token':'bad'})
assert r.status_code==403
r=c.post('/api/v1/logout',headers={'Origin':'https://www.ragab-seddik.com','X-CSRF-Token':data['csrf']})
assert r.status_code==200 and r.json()['data']['logged_out'] is True
r=c.get('/api/v1/session'); assert r.status_code==401
print('V59 SEPARATED FRONTEND CONTRACT OK')
