import os, re
os.environ.setdefault('DATABASE_URL','sqlite:///./commercial_flow_test.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import Course, User, Coupon
Base.metadata.drop_all(engine); Base.metadata.create_all(engine); seed()
db=SessionLocal()
extra=Course(title='Commercial Test Course',description='checkout test',grade='الصف الثاني الثانوي عام',price=500,published=True,teacher_id=None)
db.add(extra); db.commit(); course_id=extra.id; db.close()

def login(client,email,password):
    r=client.get('/login'); token=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':token},follow_redirects=False)
    assert r.status_code in (302,303),r.text

student=TestClient(app); login(student,'student@ragab-seddik.local','Student123!')
r=student.get(f'/checkout/{course_id}'); assert r.status_code==200 and 'الاشتراك الآمن' in r.text
assert student.get('/notifications').status_code==200
admin=TestClient(app); login(admin,'admin@ragab-seddik.local','ChangeMe123!')
r=admin.get('/admin/commerce'); assert r.status_code==200
# create 100% coupon
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=admin.post('/admin/coupons',data={'code':'FREE100','discount_percent':'100','max_uses':'1','csrf':csrf},follow_redirects=False); assert r.status_code==303
# apply coupon and activate course without payment gateway
r=student.get(f'/checkout/{course_id}?coupon=FREE100'); assert r.status_code==200
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=student.post(f'/checkout/{course_id}',data={'phone':'+201000000000','coupon_code':'FREE100','csrf':csrf},follow_redirects=False); assert r.status_code==303
assert student.get(f'/course/{course_id}').status_code==200
print('COMMERCIAL SMOKE TEST OK')
