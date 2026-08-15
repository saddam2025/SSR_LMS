import os,tempfile,re,json
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v29-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,Enrollment,ContentUnit,Lesson,LessonUnitAssignment,LessonProgress,Quiz,QuizUnitAssignment,QuizAttempt,Homework,HomeworkUnitAssignment,HomeworkSubmission,MockExamProfile,MockExamAttemptAnalysis,StudentRemediationPlan,StudentRemediationItem
from app.security import hash_password

def login(client,email,password):
    r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=True); assert r.status_code==200

def csrf_from(client,url):
    r=client.get(url); assert r.status_code==200, r.text[:300]
    m=re.search(r'name="csrf" value="([^"]+)"',r.text); assert m
    return m.group(1),r

db=SessionLocal()
a=User(name='Admin V29',email='admin-v29@example.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True)
s=User(name='Student V29',email='student-v29@example.com',password_hash=hash_password('Student123456'),role='student',is_active=True)
db.add_all([a,s]);db.commit();db.refresh(a);db.refresh(s)
c=Course(title='V29 Course',grade='الصف الثالث الثانوي',published=True,teacher_id=a.id);db.add(c);db.commit();db.refresh(c)
db.add(Enrollment(user_id=s.id,course_id=c.id,active=True,progress=50));db.commit()
u1=ContentUnit(course_id=c.id,name='Unit Weak',order_index=1,published=True);u2=ContentUnit(course_id=c.id,name='Unit Strong',order_index=2,published=True);db.add_all([u1,u2]);db.commit();db.refresh(u1);db.refresh(u2)
# weak unit: incomplete lesson + low quiz/homework + low mock
l1=Lesson(course_id=c.id,title='Weak Lesson',published=True,order_index=1);db.add(l1);db.flush();db.add(LessonUnitAssignment(lesson_id=l1.id,unit_id=u1.id));db.add(LessonProgress(user_id=s.id,lesson_id=l1.id,completed=False,watched_seconds=30))
q1=Quiz(course_id=c.id,title='Weak Quiz',published=True,time_limit_minutes=20,max_attempts=2);db.add(q1);db.flush();db.add(QuizUnitAssignment(quiz_id=q1.id,unit_id=u1.id));qa=QuizAttempt(quiz_id=q1.id,user_id=s.id,score=4,total=10,status='submitted');db.add(qa);db.flush();db.add(MockExamProfile(quiz_id=q1.id,requested_questions=10));db.add(MockExamAttemptAnalysis(attempt_id=qa.id,analysis_json=json.dumps({'by_unit':[{'name':'Unit Weak','accuracy':35}]})))
h1=Homework(course_id=c.id,title='Weak HW',published=True);db.add(h1);db.flush();db.add(HomeworkUnitAssignment(homework_id=h1.id,unit_id=u1.id));db.add(HomeworkSubmission(homework_id=h1.id,student_id=s.id,status='graded',score=45))
# strong unit
l2=Lesson(course_id=c.id,title='Strong Lesson',published=True,order_index=2);db.add(l2);db.flush();db.add(LessonUnitAssignment(lesson_id=l2.id,unit_id=u2.id));db.add(LessonProgress(user_id=s.id,lesson_id=l2.id,completed=True,watched_seconds=500))
q2=Quiz(course_id=c.id,title='Strong Quiz',published=True);db.add(q2);db.flush();db.add(QuizUnitAssignment(quiz_id=q2.id,unit_id=u2.id));db.add(QuizAttempt(quiz_id=q2.id,user_id=s.id,score=9,total=10,status='submitted'))
h2=Homework(course_id=c.id,title='Strong HW',published=True);db.add(h2);db.flush();db.add(HomeworkUnitAssignment(homework_id=h2.id,unit_id=u2.id));db.add(HomeworkSubmission(homework_id=h2.id,student_id=s.id,status='graded',score=90))
db.commit(); sid=s.id; db.close()

student=TestClient(app);login(student,'student-v29@example.com','Student123456')
csrf,r=csrf_from(student,'/learning-plan'); assert 'تحليل مستواك وخطتك العلاجية' in r.text and 'Unit Weak' in r.text and 'يحتاج علاج' in r.text and 'Unit Strong' in r.text
# plan persisted and contains actionable weak item
_db=SessionLocal();plan=_db.query(StudentRemediationPlan).filter_by(user_id=sid,active=True).first();assert plan and plan.weak_units>=1
items=_db.query(StudentRemediationItem).filter_by(plan_id=plan.id).all();assert items and any(x.priority=='high' for x in items); item=items[0]; iid=item.id;_db.close()
# toggle completion
r=student.get('/learning-plan');csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=student.post(f'/learning-plan/item/{iid}/toggle',data={'csrf':csrf},follow_redirects=False);assert r.status_code==303
_db=SessionLocal();assert _db.get(StudentRemediationItem,iid).completed is True;_db.close()
# regenerate creates a fresh active plan
csrf,_=csrf_from(student,'/learning-plan');r=student.post('/learning-plan/regenerate',data={'csrf':csrf},follow_redirects=False);assert r.status_code==303
_db=SessionLocal();assert _db.query(StudentRemediationPlan).filter_by(user_id=sid,active=True).count()==1;assert _db.query(StudentRemediationPlan).filter_by(user_id=sid).count()>=2;_db.close()
# admin can inspect the same intelligence
admin=TestClient(app);login(admin,'admin-v29@example.com','Admin123456')
r=admin.get(f'/admin/students/{sid}/learning-plan');assert r.status_code==200 and 'التحليل الذكي' in r.text and 'Unit Weak' in r.text
print('LEARNING INTELLIGENCE V29 FLOW OK')
