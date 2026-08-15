import os,tempfile,re
from datetime import datetime,timedelta
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v31-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,Enrollment,Quiz,QuizAttempt,Homework,HomeworkSubmission,Subscription,PaymentTransaction,LiveClass,SupportTicket,CommunicationCampaign
from app.security import hash_password

def login(c,e,p):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':e,'password':p,'csrf':csrf},follow_redirects=True); assert r.status_code==200

now=datetime.utcnow();db=SessionLocal()
a=User(name='Admin V31',email='admin-v31@example.com',password_hash=hash_password('Admin123456'),role='admin',is_active=True)
s=User(name='طالب يحتاج تدخل',email='student-v31@example.com',password_hash=hash_password('Student123456'),role='student',is_active=True)
db.add_all([a,s]);db.commit();db.refresh(a);db.refresh(s)
c=Course(title='English V31',grade='الصف الثالث الثانوي',published=True,teacher_id=a.id,price=500);db.add(c);db.commit();db.refresh(c)
db.add(Enrollment(user_id=s.id,course_id=c.id,active=True,progress=20,expires_at=now+timedelta(days=5)))
q=Quiz(course_id=c.id,title='Low Quiz',published=True);db.add(q);db.flush();db.add(QuizAttempt(quiz_id=q.id,user_id=s.id,score=3,total=10,status='submitted',submitted_at=now))
h=Homework(course_id=c.id,title='واجب يحتاج تصحيح',published=True,due_at=now+timedelta(days=1));db.add(h);db.flush();db.add(HomeworkSubmission(homework_id=h.id,student_id=s.id,status='submitted',answer_text='answer',submitted_at=now-timedelta(hours=2)))
db.add(Subscription(user_id=s.id,course_id=c.id,amount=500,status='active',payment_ref='v31-sub',starts_at=now-timedelta(days=20),ends_at=now+timedelta(days=3)))
db.add(PaymentTransaction(user_id=s.id,course_id=c.id,provider='manual',merchant_reference='V31PAY001',amount=500,status='paid',created_at=now,paid_at=now))
db.add(LiveClass(course_id=c.id,title='حصة V31 القادمة',provider='zoom',meeting_url='https://example.com/live',scheduled_at=now+timedelta(hours=3),duration_minutes=60,status='scheduled',created_by=a.id))
db.add(SupportTicket(user_id=s.id,subject='مشكلة دخول V31',category='technical',priority='high',status='open'))
db.add(CommunicationCampaign(created_by=a.id,title='تنبيه V31',body='رسالة',audience_type='all_students',channels='in_app',recipient_count=1))
db.commit();db.close()

cl=TestClient(app);login(cl,'admin-v31@example.com','Admin123456')
r=cl.get('/admin');assert r.status_code==200
for text in ['UI V31','لوحة القيادة اليومية','الطلاب الأكثر احتياجًا للتدخل','طالب يحتاج تدخل','واجب يحتاج تصحيح','حصة V31 القادمة','اشتراكات قريبة من الانتهاء','مشكلة دخول V31','إيراد اليوم']:
    assert text in r.text, text
assert '>500<' in r.text or '500' in r.text
print('DAILY COMMAND CENTER V31 FLOW OK')
