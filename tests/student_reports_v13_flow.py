import os,re,tempfile,zipfile,io
from datetime import datetime,timedelta
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import User,Course,Enrollment,Quiz,QuizAttempt,Homework,HomeworkSubmission
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()

def login(c):
    r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303

# enrich seed with intentionally weak performance to exercise risk detection
db=SessionLocal(); st=db.query(User).filter_by(role='student').first(); course=db.query(Course).first()
e=db.query(Enrollment).filter_by(user_id=st.id,course_id=course.id).first()
if not e: e=Enrollment(user_id=st.id,course_id=course.id,active=True,progress=20); db.add(e)
else: e.progress=20
q=Quiz(course_id=course.id,title='V13 Exam',published=True); db.add(q); db.flush(); db.add(QuizAttempt(quiz_id=q.id,user_id=st.id,score=35,total=10,status='submitted',submitted_at=datetime.utcnow()))
for i in range(2): db.add(Homework(course_id=course.id,title=f'Missed {i}',due_at=datetime.utcnow()-timedelta(days=2),published=True))
h=Homework(course_id=course.id,title='Graded',due_at=datetime.utcnow()-timedelta(days=1),published=True); db.add(h); db.flush(); db.add(HomeworkSubmission(homework_id=h.id,student_id=st.id,answer_text='x',status='graded',score=40,submitted_at=datetime.utcnow()))
db.commit(); db.close()

c=TestClient(app); login(c)
r=c.get('/admin/reports'); assert r.status_code==200 and 'تقارير أداء الطلاب' in r.text and st.name in r.text and 'يحتاج تدخل' in r.text
r=c.get('/admin/reports?risk=high'); assert r.status_code==200 and st.name in r.text
x=c.get('/admin/reports.xlsx'); assert x.status_code==200 and x.headers['content-type'].startswith('application/vnd.openxmlformats')
z=zipfile.ZipFile(io.BytesIO(x.content)); assert 'xl/worksheets/sheet1.xml' in z.namelist(); assert b'Student Performance' in z.read('xl/workbook.xml')
p=c.get('/admin/reports.pdf'); assert p.status_code==200 and p.headers['content-type'].startswith('application/pdf') and p.content.startswith(b'%PDF')
print('STUDENT REPORTS V13 FLOW OK')
