import os, tempfile, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
fd, path = tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL'] = 'sqlite:///' + path
os.environ['ENV'] = 'development'
os.environ['APP_SECRET'] = 'sherif-elements-v96-test-secret-long-enough'
os.environ['PUBLIC_BASE_URL'] = 'http://testserver'
os.environ['REQUIRE_STAFF_MFA'] = 'false'

from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, StudentProfile
from app.security import hash_password


def csrf(text):
    m = re.search(r'name="csrf" value="([^"]+)"', text)
    assert m, 'csrf token missing'
    return m.group(1)

c = TestClient(app)

# Public homepage contains every requested reference-inspired block and no dead placeholder hrefs.
r = c.get('/')
assert r.status_code == 200
for marker in (
    'id="english-hub"', 'Vocabulary', 'Tenses', 'Grammar', 'Speaking',
    'id="interactive-lab"', 'مختبر <em>الإنجليزي</em> التفاعلي',
    'id="about-ragab"', 'مستر رجب صديق',
    'id="smart-assistant"', 'مساعد المستشار الذكي معاك',
    '/english-lab#tense-lab', '/english-lab#flashcards', '/english-lab#quick-quiz',
    '/english-lab#sentence-builder', '/english-lab#speaking', '/english-lab#listening',
    '/english-lab#irregular', '/english-lab#matching', '/english-lab#reading', '/english-lab#letters',
):
    assert marker in r.text, marker
assert 'href="#"' not in r.text

# The public interactive lab is a real route and ships its JS/CSS assets.
lab = c.get('/english-lab')
assert lab.status_code == 200
for marker in ('id="tense-lab"', 'id="flashcards"', 'id="quick-quiz"', 'id="sentence-builder"',
               'id="speaking"', 'id="listening"', 'id="irregular"', 'id="matching"',
               'id="reading"', 'id="letters"', 'english-lab.js'):
    assert marker in lab.text, marker
assert c.get('/static/english-lab-core.js').status_code == 200
assert c.get('/static/english-lab.js').status_code == 200
assert c.get('/static/sherif-inspired-v96.css').status_code == 200
assert c.get('/register').status_code == 200
assert c.get('/login').status_code == 200

# Logged-in student destinations behind homepage buttons are also live.
db = SessionLocal()
u = User(name='Sherif Elements Student', email='student-elements@test.local', password_hash=hash_password('Student123456'), role='student', is_active=True)
db.add(u); db.flush(); db.add(StudentProfile(user_id=u.id, phone='01012345678', grade='الصف الأول الثانوي')); db.commit(); db.close()
login_page = c.get('/login')
login = c.post('/login', data={'email':'student-elements@test.local','password':'Student123456','csrf':csrf(login_page.text)}, follow_redirects=False)
assert login.status_code == 303
for url in ('/dashboard','/support','/search','/study-plan','/smart-tutor','/english-tools'):
    rr = c.get(url)
    assert rr.status_code == 200, (url, rr.status_code, rr.text[:200])

# Home page in authenticated mode resolves to real internal endpoints rather than auth errors.
auth_home = c.get('/')
assert auth_home.status_code == 200
assert 'href="/support"' in auth_home.text
assert 'href="/smart-tutor"' in auth_home.text

print('SHERIF INTERACTIVE ELEMENTS V96 FLOW OK')
