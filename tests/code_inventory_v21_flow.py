import os,tempfile,re
from datetime import datetime,timedelta
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v21-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,ActivationCodeBatch,ActivationCodeInventory,ActivationCode,ActivationRedemption,Enrollment
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal(); admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True); st=User(name='Student',email='student@test.local',password_hash=hash_password('StudentPass12345'),role='student',is_active=True); course=Course(title='English V21',grade='3rd',published=True); db.add_all([admin,st,course]); db.commit(); cid=course.id; sid=st.id; db.close()
client=TestClient(app)
def csrf_get(path):
 r=client.get(path); assert r.status_code==200,(path,r.status_code,r.text[:300]); m=re.search(r'name="csrf" value="([^"]+)"',r.text); assert m,path; return m.group(1),r
csrf,_=csrf_get('/login'); r=client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
csrf,r=csrf_get('/admin/code-inventory'); assert 'مخزون أكواد الاشتراك الجماعية' in r.text
exp=(datetime.utcnow()+timedelta(days=30)).strftime('%Y-%m-%dT%H:%M')
r=client.post('/admin/code-inventory/batches',data={'course_id':cid,'name':'Center A - August','quantity':'12','distributor':'Center A','expires_at':exp,'notes':'V21 test batch','csrf':csrf},follow_redirects=False); assert r.status_code==303, r.text
loc=r.headers['location']; assert loc.startswith('/admin/code-inventory/')
db=SessionLocal(); b=db.query(ActivationCodeBatch).one(); assert b.quantity==12 and b.distributor=='Center A'; assert db.query(ActivationCodeInventory).filter_by(batch_id=b.id).count()==12; assert db.query(ActivationCode).filter_by(course_id=cid).count()==12; bid=b.id; first=db.query(ActivationCodeInventory).filter_by(batch_id=bid).order_by(ActivationCodeInventory.serial_no).first(); code=db.get(ActivationCode,first.activation_code_id).code; db.close()
r=client.get(loc); assert r.status_code==200 and code in r.text and 'Center A' in r.text
rx=client.get(f'/admin/code-inventory/export/{bid}.xlsx'); assert rx.status_code==200 and rx.content[:2]==b'PK'
rp=client.get(f'/admin/code-inventory/export/{bid}.pdf'); assert rp.status_code==200 and rp.content[:4]==b'%PDF'
# logout/login student and redeem one code
client.get('/logout',follow_redirects=False)
csrf,_=csrf_get('/login'); r=client.post('/login',data={'email':'student@test.local','password':'StudentPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
# any page with csrf
r=client.get('/dashboard'); m=re.search(r'name="csrf" value="([^"]+)"',r.text); csrf=m.group(1) if m else client.cookies.get('csrf','')
if not csrf:
 # profile reliably contains form csrf
 csrf,_=csrf_get('/profile')
r=client.post('/activate-code',data={'code':code,'csrf':csrf},follow_redirects=False); assert r.status_code==303,(r.status_code,r.text)
db=SessionLocal(); ac=db.query(ActivationCode).filter_by(code=code).one(); assert ac.used_count==1; assert db.query(ActivationRedemption).filter_by(activation_code_id=ac.id,user_id=sid).count()==1; assert db.query(Enrollment).filter_by(user_id=sid,course_id=cid,active=True).count()==1; db.close()
print('CODE INVENTORY V21 FLOW OK')
