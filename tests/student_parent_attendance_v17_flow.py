import os,re,tempfile
from datetime import datetime
os.environ['ENV']='development'; os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db'); os.environ['SEED_DEMO_USERS']='true'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import User,StudentAttendance,StudentStreak
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()

def csrf(html):
    m=re.search(r'name="csrf" value="([^"]+)"',html); assert m; return m.group(1)
def login(c,email,password):
    r=c.get('/login'); t=csrf(r.text); return c.post('/login',data={'email':email,'password':password,'csrf':t},follow_redirects=True)

db=SessionLocal(); st=db.query(User).filter_by(role='student').first(); today=datetime.utcnow().strftime('%Y-%m-%d')
db.add(StudentAttendance(user_id=st.id,attendance_date=today,status='excused',source='manual',note='اختبار V17'))
row=db.query(StudentStreak).filter_by(user_id=st.id).first()
if row: row.current_days=4; row.best_days=max(row.best_days,7)
else: db.add(StudentStreak(user_id=st.id,current_days=4,best_days=7,last_activity_date=today))
db.commit(); db.close()

with TestClient(app) as c:
    r=login(c,'student@ragab-seddik.local','Student123!'); assert r.status_code==200
    assert 'نشاطي وحضوري' in r.text and 'Streak حالي' in r.text and 'بعذر' in r.text
with TestClient(app) as c:
    r=login(c,'parent@ragab-seddik.local','Parent12345!'); assert r.status_code==200
    assert 'نشاط أسبوعي' in r.text and 'Streak حالي' in r.text
    m=re.search(r'/parent/report/(\d+)',r.text); assert m
    rr=c.get(m.group(0)); assert rr.status_code==200 and 'الحضور والنشاط خلال 7 أيام' in rr.text and 'بعذر' in rr.text
print('STUDENT/PARENT ATTENDANCE V17 FLOW OK')
