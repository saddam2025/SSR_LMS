import re
from fastapi.testclient import TestClient
from app.seed import run
run()
from app.main import app

c=TestClient(app)
r=c.get('/health'); assert r.status_code==200 and r.json()['status']=='ok'
r=c.get('/ready'); assert r.status_code==200 and r.json()['database']=='ok'
login=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',login.text).group(1)
r=c.post('/login',data={'email':'student@ragab-seddik.local','password':'Student123!','csrf':csrf},follow_redirects=False)
assert r.status_code in (302,303)
r=c.get('/api/v1/courses'); assert r.status_code==200 and 'data' in r.json()
r=c.get('/api/v1/me/summary'); assert r.status_code==200 and 'active_courses' in r.json()['data']
# Metrics are admin-only.
r=c.get('/internal/metrics', follow_redirects=False); assert r.status_code==303 and r.headers['location'].startswith('/dashboard')
print('SCALE READY FEATURE TEST OK')
