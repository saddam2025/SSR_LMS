import re
from fastapi.testclient import TestClient
from app.main import app
from app.seed import run
from app.db import SessionLocal
from app.models import ActiveSession, Device

run()
c = TestClient(app)
r = c.get('/login')
csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
r = c.post('/login', data={
    'email':'admin@ragab-seddik.local',
    'password':'ChangeMe123!',
    'csrf':csrf,
}, follow_redirects=False)
assert r.status_code == 303
assert c.get('/admin/security').status_code == 200

db = SessionLocal()
assert db.query(ActiveSession).filter(ActiveSession.revoked_at.is_(None)).count() >= 1
assert db.query(Device).count() >= 1
db.close()
print('SECURITY SMOKE TEST OK')
