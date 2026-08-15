import os, tempfile
os.environ.setdefault('ENV','development')
os.environ.setdefault('APP_SECRET','dev-secret-change-this-immediately')
os.environ['DATABASE_URL']='sqlite:///' + tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine)
client=TestClient(app)
r=client.get('/register'); assert r.status_code==200
csrf=client.cookies.get('lms_session'); assert csrf is not None
# pull csrf from rendered form
import re
m=re.search(r'name="csrf" value="([^"]+)"', r.text); assert m
payload={'csrf':m.group(1),'name':'طالب اختبار','email':'teststudent@example.org','phone':'01012345678','grade':'الصف الأول الثانوي','password':'StrongPass12345','password_confirm':'StrongPass12345'}
r=client.post('/register',data=payload,follow_redirects=False); assert r.status_code==303, r.text
r=client.get('/dashboard'); assert r.status_code==200
# duplicate registration should be rejected (new session)
client.post('/logout', data={'csrf': re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)} if re.search(r'name="csrf" value="([^"]+)"', r.text) else {})
r=client.get('/register'); m=re.search(r'name="csrf" value="([^"]+)"', r.text); assert m
r=client.post('/register',data={**payload,'csrf':m.group(1)},follow_redirects=False); assert r.status_code in (409,429)
print('ULTIMATE RELEASE TEST OK')
