import os,tempfile,re,json
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v30-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,Enrollment,ContentUnit,Lesson,LessonUnitAssignment,LessonProgress,Quiz,QuizUnitAssignment,QuizAttempt,Homework,HomeworkUnitAssignment,HomeworkSubmission,StudyAssistantLog
from app.security import hash_password

def login(c,e,p):
 r=c.get('/login');csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1);r=c.post('/login',data={'email':e,'password':p,'csrf':csrf},follow_redirects=True);assert r.status_code==200

db=SessionLocal();a=User(name='Admin V30',email='a30@x.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True);s=User(name='Student V30',email='s30@x.com',password_hash=hash_password('Student123456'),role='student',is_active=True);db.add_all([a,s]);db.commit();db.refresh(a);db.refresh(s)
c=Course(title='English V30',grade='الصف الثالث الثانوي',published=True,teacher_id=a.id);db.add(c);db.commit();db.refresh(c);db.add(Enrollment(user_id=s.id,course_id=c.id,active=True,progress=30));u=ContentUnit(course_id=c.id,name='Unit Grammar',order_index=1,published=True);db.add(u);db.commit();db.refresh(u)
l=Lesson(course_id=c.id,title='Present Perfect',body='Present perfect connects a past action with the present. Use have or has with the past participle. We use since for a starting point and for for a duration.',published=True,order_index=1);db.add(l);db.flush();db.add(LessonUnitAssignment(lesson_id=l.id,unit_id=u.id));db.add(LessonProgress(user_id=s.id,lesson_id=l.id,completed=False,watched_seconds=10));q=Quiz(course_id=c.id,title='Grammar Quiz',published=True);db.add(q);db.flush();db.add(QuizUnitAssignment(quiz_id=q.id,unit_id=u.id));db.add(QuizAttempt(quiz_id=q.id,user_id=s.id,score=3,total=10,status='submitted'));h=Homework(course_id=c.id,title='Grammar HW',published=True,lesson_id=l.id,instructions='Use since and for in five sentences.');db.add(h);db.flush();db.add(HomeworkUnitAssignment(homework_id=h.id,unit_id=u.id));db.add(HomeworkSubmission(homework_id=h.id,student_id=s.id,status='graded',score=40));db.commit();lid=l.id;sid=s.id;db.close()
cl=TestClient(app);login(cl,'s30@x.com','Student123456')
r=cl.get('/smart-tutor');assert r.status_code==200 and 'مساعد المستشار الشخصي' in r.text and 'Unit Grammar' in r.text and 'ذاكر مع المساعد' in r.text
r=cl.get(f'/lesson/{lid}');assert r.status_code==200 and 'شرح مبسط حسب مستواي' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=cl.post(f'/lesson/{lid}/assistant',data={'csrf':csrf,'mode':'review','question':'راجع لي since و for'},follow_redirects=True);assert r.status_code==200 and 'مراجعة مركزة لمستواك' in r.text and 'مستواك الحالي في Unit Grammar' in r.text and 'since' in r.text
_db=SessionLocal();log=_db.query(StudyAssistantLog).filter_by(user_id=sid,lesson_id=lid).first();assert log and log.source_kind=='personalized_review';_db.close()
r=cl.get('/smart-tutor');assert 'راجع لي since و for' in r.text
print('SMART TUTOR V30 FLOW OK')
