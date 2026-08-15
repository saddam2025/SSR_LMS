import os, tempfile
from pathlib import Path
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development'; os.environ['APP_SECRET']='v26-test-secret'; os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,Lesson,Enrollment,LessonProgress,Quiz,Question,QuizAttempt,Homework,HomeworkSubmission,CourseCompletionPolicy,CourseCertificate
from app.security import hash_password
db=SessionLocal()
admin=User(name='Admin V26',email='admin-v26@example.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True); db.add(admin)
student=User(name='طالب V26',email='v26@example.com',password_hash=hash_password('Student123456'),role='student',is_active=True); db.add(student); db.commit(); db.refresh(admin); db.refresh(student)
c=Course(title='V26 Certificate Course',grade='الصف الثالث الثانوي',published=True,teacher_id=admin.id if admin else None); db.add(c); db.commit(); db.refresh(c)
l=Lesson(course_id=c.id,title='Lesson 1',published=True,order_index=1); db.add(l)
q=Quiz(course_id=c.id,title='Quiz 1',published=True,max_attempts=2); db.add(q)
h=Homework(course_id=c.id,title='HW 1',published=True); db.add(h); db.commit()
db.add(Enrollment(user_id=student.id,course_id=c.id,active=True,progress=100))
db.add(CourseCompletionPolicy(course_id=c.id,require_all_lessons=True,require_quizzes=True,minimum_quiz_average=60,require_homeworks=True,minimum_homework_average=60,certificate_enabled=True))
db.add(LessonProgress(user_id=student.id,lesson_id=l.id,completed=True,watched_seconds=100))
db.add(QuizAttempt(quiz_id=q.id,user_id=student.id,score=8,total=10,status='submitted'))
db.add(HomeworkSubmission(homework_id=h.id,student_id=student.id,answer_text='done',status='graded',score=80,submitted_at=None,graded_at=None))
db.commit(); sid=student.id; cid=c.id; db.close()
client=TestClient(app)
# login through form csrf
r=client.get('/login'); assert r.status_code==200
# extract csrf
import re
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
student_email='v26@example.com' if 'v26@example.com' else ''
# student might be seed user with unknown password, force password
db=SessionLocal(); st=db.get(User,sid); st.password_hash=hash_password('Student123456'); email=st.email; db.commit(); db.close()
r=client.post('/login',data={'email':email,'password':'Student123456','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=client.get(f'/course/{cid}'); assert r.status_code==200, r.text[:300]; assert 'مبروك' in r.text
# certificate issued
db=SessionLocal(); cert=db.query(CourseCertificate).filter_by(user_id=sid,course_id=cid).first(); assert cert and not cert.revoked_at; cert_id=cert.id; code=cert.verification_code; db.close()
r=client.get(f'/certificate/{cert_id}'); assert r.status_code==200 and code in r.text
r=client.get(f'/certificate/verify/{code}'); assert r.status_code==200 and 'شهادة صحيحة' in r.text
r=client.get(f'/certificate/{cert_id}/qr.png'); assert r.status_code==200 and r.headers['content-type'].startswith('image/png') and len(r.content)>500
r=client.get(f'/certificate/{cert_id}/download.pdf'); assert r.status_code==200 and r.content.startswith(b'%PDF') and len(r.content)>2000; Path(os.getenv('TMPDIR','/tmp'), 'v26-certificate-sample.pdf').write_bytes(r.content)
print('COURSE COMPLETION V26 FLOW OK')
