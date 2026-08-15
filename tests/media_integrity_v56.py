import os,re
os.environ['DATABASE_URL']='sqlite:///./media_structure_test.db'; os.environ.pop('ENV',None)
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import Course,Lesson
Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed(); c=TestClient(app)
def csrf(path):
 r=c.get(path); return re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
x=csrf('/login'); r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':x},follow_redirects=False); assert r.status_code in (302,303)
db=SessionLocal(); co=db.query(Course).first(); le=db.query(Lesson).filter_by(course_id=co.id).first(); cid,lid=co.id,le.id; db.close()
def up(fn,mime,data):
 x=csrf(f'/admin/course/{cid}'); return c.post(f'/admin/course/{cid}/media',data={'lesson_id':lid,'csrf':x},files={'file':(fn,data,mime)},follow_redirects=False)
assert up('broken.pdf','application/pdf',b'%PDF-1.7\nthis is not a real pdf').status_code==415
assert up('broken.jpg','image/jpeg',b'\xff\xd8\xff'+b'garbage'*100).status_code==415
assert up('broken.png','image/png',b'\x89PNG\r\n\x1a\n'+b'garbage'*100).status_code==415
print('MEDIA STRUCTURE HARDENING OK')
