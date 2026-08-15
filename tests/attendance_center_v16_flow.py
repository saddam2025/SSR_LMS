import os,re,tempfile
from datetime import datetime,timedelta
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import User,StudentAttendance,CommunicationCampaign,Notification,ActiveSession
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()

def login(c):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303

db=SessionLocal(); st=db.query(User).filter_by(role='student').first(); sid=st.id
# Force stale activity if session exists.
for ses in db.query(ActiveSession).filter_by(user_id=sid).all(): ses.last_seen_at=datetime.utcnow()-timedelta(days=10)
db.commit(); db.close()

c=TestClient(app); login(c)
r=c.get('/admin/attendance'); assert r.status_code==200 and 'الحضور والمتابعة اليومية' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); today=datetime.utcnow().strftime('%Y-%m-%d')
r=c.post('/admin/attendance/mark',data={'student_id':sid,'attendance_date':today,'status':'excused','note':'عذر اختباري','csrf':csrf},follow_redirects=False); assert r.status_code==303

db=SessionLocal(); a=db.query(StudentAttendance).filter_by(user_id=sid,attendance_date=today).one(); assert a.status=='excused' and a.source=='manual'; db.close()
r=c.get('/admin/attendance'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/admin/attendance/notify-inactive',data={'days':3,'csrf':csrf},follow_redirects=False); assert r.status_code==303

db=SessionLocal(); camp=db.query(CommunicationCampaign).filter_by(audience_type='inactive').order_by(CommunicationCampaign.id.desc()).first(); assert camp is not None
assert db.query(Notification).filter_by(title='متابعة النشاط على منصة المستشار').count()>=1; db.close()
print('ATTENDANCE CENTER V16 FLOW OK')
