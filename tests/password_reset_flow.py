import os, re
os.environ.setdefault('ENV','development')
os.environ.setdefault('DATABASE_URL','sqlite:///./password_reset_test.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine
from app.seed import run

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); run()
c=TestClient(app)
r=c.get('/forgot-password'); assert r.status_code==200
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/forgot-password/request',data={'phone':'01000000001','csrf':csrf}); assert r.status_code==200
m=re.search(r'رمز التطوير:\s*(\d{6})',r.text); assert m, r.text
code=m.group(1)
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/forgot-password/verify',data={'code':code,'csrf':csrf}); assert r.status_code==200
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/forgot-password/complete',data={'password':'NewStudentPass123!','password_confirm':'NewStudentPass123!','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/login',data={'email':'student@ragab-seddik.local','password':'NewStudentPass123!','csrf':csrf},follow_redirects=False); assert r.status_code==303
print('PASSWORD RESET FLOW OK')
