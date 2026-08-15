import inspect, os, re, tempfile
from collections import Counter
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL'] = 'sqlite:///' + path
os.environ['APP_SECRET'] = 'v77-domain-secret-long-enough-123456'
os.environ['ENV'] = 'test'
os.environ['REQUIRE_STAFF_MFA'] = 'false'

from app.main import app
import app.main as main_mod
import app.routers.assessments_admin as assessments_router
import app.routers.push_notifications as push_router
import app.routers.activation_codes as codes_router
from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password

Base.metadata.create_all(bind=engine)
db=SessionLocal(); db.add(User(name='Student V77',email='student77@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True)); db.commit(); db.close()

source=inspect.getsource(main_mod)
for marker in [
    '@app.post("/admin/course/{course_id}/quizzes")',
    '@app.get("/admin/quiz/{quiz_id}"',
    '@app.post("/admin/course/{course_id}/homework")',
    '@app.get("/api/mobile/push/config")',
    '@app.get("/admin/code-inventory"',
    '@app.post("/activate-code")',
]:
    assert marker not in source, marker

assert '/admin/quiz/{quiz_id}' in inspect.getsource(assessments_router)
assert '/admin/homework/{homework_id}/grade' in inspect.getsource(assessments_router)
assert '/api/mobile/push/register' in inspect.getsource(push_router)
assert '/admin/code-inventory' in inspect.getsource(codes_router)

pairs=[]
for route in app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods or []:
            if method not in {'HEAD','OPTIONS'}: pairs.append((method, route.path))
counts=Counter(pairs); dupes={k:v for k,v in counts.items() if v>1}; assert not dupes, dupes
required={
 ('POST','/admin/course/{course_id}/quizzes'), ('GET','/admin/quiz/{quiz_id}'),
 ('POST','/admin/course/{course_id}/homework'), ('POST','/admin/homework/{homework_id}/grade'),
 ('GET','/api/mobile/push/config'), ('POST','/api/mobile/push/register'),
 ('GET','/admin/code-inventory'), ('POST','/activate-code'),
}
assert required.issubset(set(pairs)), required-set(pairs)

c=TestClient(app)
login=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"', login.text).group(1)
r=c.post('/login', data={'email':'student77@example.com','password':'StudentPass12345','csrf':csrf}, follow_redirects=False); assert r.status_code==303
r=c.get('/api/mobile/push/config'); assert r.status_code==200 and 'csrf' in r.json() and 'push' in r.json()
r=c.post('/api/mobile/push/register',json={'token':'x'*80,'installation_id':'v77','device_name':'Android','app_version':'77','csrf':'bad'}); assert r.status_code==403
print('V77 DOMAIN EXTRACTION: PASS')
