import os,re,tempfile
from datetime import datetime,timedelta
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import User,Course,Enrollment,Subscription,StudentProfile,Homework,Notification,CommunicationCampaign,CommunicationDelivery
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()

def login(c):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303

# Seed audience facts.
db=SessionLocal(); st=db.query(User).filter_by(role='student').first(); course=db.query(Course).first()
prof=db.query(StudentProfile).filter_by(user_id=st.id).first()
if not prof: prof=StudentProfile(user_id=st.id,grade='الصف الأول الثانوي',phone='01000000000'); db.add(prof)
else: prof.grade='الصف الأول الثانوي'; prof.phone='01000000000'
e=db.query(Enrollment).filter_by(user_id=st.id,course_id=course.id).first()
if not e: db.add(Enrollment(user_id=st.id,course_id=course.id,active=True))
db.add(Subscription(user_id=st.id,course_id=course.id,status='active',ends_at=datetime.utcnow()+timedelta(days=3)))
db.add(Homework(course_id=course.id,title='V15 overdue',due_at=datetime.utcnow()-timedelta(days=2),published=True))
db.commit(); sid=st.id; cid=course.id; db.close()

c=TestClient(app); login(c)
r=c.get('/admin/communications'); assert r.status_code==200 and 'مركز الإشعارات والتواصل' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
# In-app + unconfigured SMS: internal succeeds, external is audited without crashing.
data={'title':'رسالة V15','body':'اختبار مركز التواصل','audience_type':'course','audience_value':str(cid),'channels':['in_app','sms'],'csrf':csrf}
r=c.post('/admin/communications/send',data=data,follow_redirects=False); assert r.status_code==303

db=SessionLocal(); camp=db.query(CommunicationCampaign).filter_by(title='رسالة V15').one(); assert camp.recipient_count>=1
assert db.query(Notification).filter_by(user_id=sid,title='رسالة V15').count()==1
rows=db.query(CommunicationDelivery).filter_by(campaign_id=camp.id,user_id=sid).all(); statuses={(x.channel,x.status) for x in rows}; assert ('in_app','sent') in statuses and ('sms','not_configured') in statuses
db.close()
# Smart expiring alert.
r=c.get('/admin/communications'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post('/admin/communications/quick',data={'preset':'expiring','channel':'in_app','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); assert db.query(Notification).filter_by(user_id=sid,title='اشتراكك يقترب من الانتهاء').count()>=1; db.close()
print('COMMUNICATION CENTER V15 FLOW OK')
