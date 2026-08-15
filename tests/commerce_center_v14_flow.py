import os,re,tempfile
from datetime import datetime,timedelta
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import User,Course,Coupon,ActivationCode,Subscription,PaymentTransaction,Enrollment
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()

def login(c):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303

c=TestClient(app); login(c)
r=c.get('/admin/commerce'); assert r.status_code==200 and 'مركز المبيعات والاشتراكات' in r.text and 'إجمالي الإيراد' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
db=SessionLocal(); st=db.query(User).filter_by(role='student').first(); course=db.query(Course).first(); sid=st.id; cid=course.id; db.close()
# coupon with expiry
exp=(datetime.utcnow()+timedelta(days=10)).strftime('%Y-%m-%dT%H:%M')
r=c.post('/admin/coupons',data={'code':'V14SAVE','discount_percent':'25','max_uses':'5','expires_at':exp,'csrf':csrf},follow_redirects=False); assert r.status_code==303
# activation code with expiry
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/admin/activation-codes',data={'course_id':cid,'code':'V14ACT','max_uses':'3','expires_at':exp,'csrf':csrf},follow_redirects=False); assert r.status_code==303
# manual subscription grant
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/admin/subscriptions/grant',data={'user_id':sid,'course_id':cid,'duration_days':'30','amount':'150','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); cp=db.query(Coupon).filter_by(code='V14SAVE').one(); ac=db.query(ActivationCode).filter_by(code='V14ACT').one(); sub=db.query(Subscription).filter_by(user_id=sid,course_id=cid).order_by(Subscription.id.desc()).first(); assert cp.expires_at and ac.expires_at and sub and sub.ends_at and sub.status=='active'; subid=sub.id; old_end=sub.ends_at; e=db.query(Enrollment).filter_by(user_id=sid,course_id=cid).first(); assert e and e.active; db.close()
# extend and cancel/reactivate
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/subscriptions/{subid}/extend',data={'days':'15','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); sub=db.get(Subscription,subid); assert sub.ends_at>old_end; db.close()
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/subscriptions/{subid}/status',data={'status':'cancelled','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); assert db.get(Subscription,subid).status=='cancelled'; assert not db.query(Enrollment).filter_by(user_id=sid,course_id=cid).first().active; db.close()
# toggles
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
db=SessionLocal(); cpid=db.query(Coupon).filter_by(code='V14SAVE').one().id; acid=db.query(ActivationCode).filter_by(code='V14ACT').one().id; db.close()
assert c.post(f'/admin/coupons/{cpid}/toggle',data={'csrf':csrf},follow_redirects=False).status_code==303
r=c.get('/admin/commerce'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
assert c.post(f'/admin/activation-codes/{acid}/toggle',data={'csrf':csrf},follow_redirects=False).status_code==303
print('COMMERCE CENTER V14 FLOW OK')
