import os,re,tempfile
from datetime import datetime,timedelta
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import Course,Homework,HomeworkSubmission,User,Enrollment
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()
def login(c):
 r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303
c=TestClient(app); login(c)
db=SessionLocal(); course=db.query(Course).first(); student=db.query(User).filter_by(role='student').first();
if not db.query(Enrollment).filter_by(user_id=student.id,course_id=course.id).first(): db.add(Enrollment(user_id=student.id,course_id=course.id,active=True))
h=Homework(course_id=course.id,title='V12 Homework',instructions='Answer',due_at=datetime.utcnow()-timedelta(days=1),published=True); db.add(h); db.commit();
sub=HomeworkSubmission(homework_id=h.id,student_id=student.id,answer_text='My answer',status='submitted',submitted_at=datetime.utcnow()); db.add(sub); db.commit(); hid=h.id; sid=student.id; db.close()
r=c.get('/teacher/assessment'); assert r.status_code==200 and 'مركز التقييم والتصحيح' in r.text and 'V12 Homework' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/homework/{hid}/revision',data={'student_id':sid,'feedback':'راجع النقطة الثانية','return_to':'assessment','csrf':csrf},follow_redirects=False); assert r.status_code==303 and r.headers['location']=='/teacher/assessment'
db=SessionLocal(); sub=db.query(HomeworkSubmission).filter_by(homework_id=hid,student_id=sid).first(); assert sub.status=='revision_requested' and 'راجع' in sub.feedback; db.close()
# Student resubmission behavior is covered by existing homework route; return status to submitted for grade flow.
db=SessionLocal(); sub=db.query(HomeworkSubmission).filter_by(homework_id=hid,student_id=sid).first(); sub.status='submitted'; db.commit(); db.close()
r=c.get('/teacher/assessment'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/homework/{hid}/grade',data={'student_id':sid,'score':'88.5','feedback':'جيد جدًا','return_to':'assessment','csrf':csrf},follow_redirects=False); assert r.status_code==303 and r.headers['location']=='/teacher/assessment'
db=SessionLocal(); sub=db.query(HomeworkSubmission).filter_by(homework_id=hid,student_id=sid).first(); assert sub.status=='graded' and abs(sub.score-88.5)<0.01; db.close()
print('ASSESSMENT CENTER V12 FLOW OK')
