import os, re, tempfile
os.environ.setdefault('ENV','development')
os.environ['DATABASE_URL']='sqlite:///' + tempfile.mktemp(suffix='.db')
os.environ['REQUIRE_STAFF_MFA']='false'  # Navigation regression runs without forcing MFA enrollment.
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine
from app.seed import run as seed
from app.security import REQUIRE_STAFF_MFA

Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()
assert REQUIRE_STAFF_MFA is False

def login(client, email, password, expected):
    r=client.get('/login'); assert r.status_code==200
    csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=False)
    assert r.status_code==303, r.text
    assert r.headers['location']==expected, (email, r.headers.get('location'))

def check(client, paths):
    for path in paths:
        rr=client.get(path,follow_redirects=False)
        assert rr.status_code==200, (path, rr.status_code, rr.text[:180])

admin=TestClient(app); login(admin,'admin@ragab-seddik.local','ChangeMe123!','/admin')
check(admin,['/admin','/admin/users','/admin/students','/admin/commerce','/admin/security','/admin/system-status','/search','/notifications','/account/security'])

legacy_teacher=TestClient(app)
assert legacy_teacher.get('/teacher', follow_redirects=False).status_code == 303

student=TestClient(app); login(student,'student@ragab-seddik.local','Student123!','/dashboard')
check(student,['/dashboard','/english-tools','/study-plan','/leaderboard','/profile','/search','/notifications','/account/security'])

parent=TestClient(app); login(parent,'parent@ragab-seddik.local','Parent12345!','/parent')
check(parent,['/parent','/search','/notifications','/account/security'])

home=TestClient(app).get('/')
assert home.status_code==200
assert 'wa.me/201060309494' in home.text
assert '/static/branding/ragab-seddik-hero-2026.webp' in home.text
asset=TestClient(app).get('/static/branding/ragab-seddik-hero-2026.webp')
assert asset.status_code==200 and asset.headers.get('content-type','').startswith('image/')
print('SINGLE-TEACHER NAVIGATION + DASHBOARDS + WHATSAPP + OPTIMIZED HERO OK')
