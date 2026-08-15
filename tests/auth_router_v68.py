import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL'] = 'sqlite:///' + path
os.environ.setdefault('ENV', 'test')
os.environ.setdefault('APP_SECRET', 'v68-auth-router-secret')
os.environ.setdefault('REQUIRE_STAFF_MFA', 'false')

from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.models import User, StudentProfile
from app.routers import auth
from app.security import hash_password

expected = {
    '/register', '/forgot-password', '/forgot-password/request', '/forgot-password/verify',
    '/forgot-password/complete', '/login', '/mfa', '/account/security',
    '/account/security/mfa/enable', '/account/password', '/logout', '/otp-login',
    '/otp-login/request', '/otp-login/verify',
}
router_paths = {r.path for r in auth.router.routes}
assert expected <= router_paths, expected - router_paths

main_text = Path('app/main.py').read_text()
for p in ['/login', '/register', '/forgot-password', '/mfa', '/account/security', '/logout', '/otp-login']:
    assert f'@app.get("{p}"' not in main_text and f'@app.post("{p}"' not in main_text, p

seen = set()
for r in app.routes:
    for method in (getattr(r, 'methods', None) or set()):
        key = (method, r.path)
        assert key not in seen, f'duplicate route: {key}'
        seen.add(key)

Base.metadata.create_all(bind=engine)
db = SessionLocal()
u = User(name='V68 Student', email='v68@example.com', password_hash=hash_password('StudentPass12345'), role='student', is_active=True)
db.add(u); db.flush(); db.add(StudentProfile(user_id=u.id, phone='01012345678', grade='الصف الثالث الثانوي')); db.commit(); db.close()

c = TestClient(app)
page = c.get('/login'); assert page.status_code == 200
csrf = page.text.split('name="csrf" value="', 1)[1].split('"', 1)[0]
r = c.post('/login', data={'email':'v68@example.com','password':'StudentPass12345','csrf':csrf}, follow_redirects=False)
assert r.status_code == 303, r.status_code
assert c.get('/dashboard', follow_redirects=False).status_code in {200,302,303}

# Logout remains CSRF protected after extraction.
r = c.post('/logout', data={'csrf':'bad'}, follow_redirects=False)
assert r.status_code == 403, r.status_code
print('V68 AUTH ROUTER + SERVICE EXTRACTION: PASS')
