import os,tempfile,re
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v23-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,Lesson,Quiz,Question,QuizQuestionSetting,Homework,ContentUnit,LessonUnitAssignment,QuizUnitAssignment,HomeworkUnitAssignment,CourseAcademicPeriod
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
c=Course(title='English Third Secondary 2026',grade='الصف الثالث الثانوي',published=True,description='Main course')
db.add_all([admin,c]); db.commit(); db.refresh(c)
u=ContentUnit(course_id=c.id,name='Unit 1',description='Grammar',order_index=1,published=True); db.add(u); db.flush()
l=Lesson(course_id=c.id,title='Lesson One',body='Body',video_url='https://example.com/v',published=True,order_index=1); db.add(l); db.flush(); db.add(LessonUnitAssignment(lesson_id=l.id,unit_id=u.id))
q=Quiz(course_id=c.id,title='Quiz One',published=True,time_limit_minutes=20,max_attempts=2,shuffle_questions=False); db.add(q); db.flush(); db.add(QuizUnitAssignment(quiz_id=q.id,unit_id=u.id))
qq=Question(quiz_id=q.id,text='Q?',option_a='A',option_b='B',option_c='C',option_d='D',correct='A'); db.add(qq); db.flush(); db.add(QuizQuestionSetting(question_id=qq.id,position=1,points=3))
h=Homework(course_id=c.id,lesson_id=l.id,title='Homework One',instructions='Do it',published=True); db.add(h); db.flush(); db.add(HomeworkUnitAssignment(homework_id=h.id,unit_id=u.id))
db.commit(); cid,uid=c.id,u.id; db.close()
client=TestClient(app)
r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=client.get('/teacher/content'); assert r.status_code==200 and 'السنة غير محددة' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post(f'/teacher/content/course/{cid}/period',data={'academic_year':'2026/2027','term':'الترم الأول','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); p=db.query(CourseAcademicPeriod).filter_by(course_id=cid).one(); assert p.academic_year=='2026/2027' and p.term=='الترم الأول'; db.close()
# Clone the unit inside the same course and verify independent content.
r=client.post(f'/teacher/content/unit/{uid}/clone',data={'target_course_id':cid,'new_name':'Unit 1 Copy','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); uc=db.query(ContentUnit).filter_by(course_id=cid,name='Unit 1 Copy').one();
assert db.query(LessonUnitAssignment).filter_by(unit_id=uc.id).count()==1
assert db.query(QuizUnitAssignment).filter_by(unit_id=uc.id).count()==1
assert db.query(HomeworkUnitAssignment).filter_by(unit_id=uc.id).count()==1
cloned_quiz_id=db.query(QuizUnitAssignment).filter_by(unit_id=uc.id).one().quiz_id
cloned_q=db.query(Question).filter_by(quiz_id=cloned_quiz_id).one(); setting=db.query(QuizQuestionSetting).filter_by(question_id=cloned_q.id).one(); assert setting.points==3
assert db.get(Quiz,cloned_quiz_id).published is False
db.close()
# Clone full course to a new academic period.
r=client.post(f'/teacher/content/course/{cid}/clone',data={'academic_year':'2027/2028','term':'الترم الثاني','new_title':'English Third Secondary 2027','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); nc=db.query(Course).filter_by(title='English Third Secondary 2027').one(); np=db.query(CourseAcademicPeriod).filter_by(course_id=nc.id).one(); assert np.academic_year=='2027/2028' and np.term=='الترم الثاني'; assert nc.published is False
# Source currently has 2 units because we cloned one first; both should be copied.
assert db.query(ContentUnit).filter_by(course_id=nc.id).count()==2
assert db.query(Lesson).filter_by(course_id=nc.id).count()==2
assert db.query(Quiz).filter_by(course_id=nc.id).count()==2
assert db.query(Homework).filter_by(course_id=nc.id).count()==2
assert all(not x.published for x in db.query(Lesson).filter_by(course_id=nc.id).all())
assert all(not x.published for x in db.query(Quiz).filter_by(course_id=nc.id).all())
assert all(not x.published for x in db.query(Homework).filter_by(course_id=nc.id).all())
db.close()
r=client.get('/teacher/content'); assert '2026/2027' in r.text and 'الترم الأول' in r.text and 'English Third Secondary 2027' in r.text and '2027/2028' in r.text
print('ACADEMIC STRUCTURE V23 FLOW OK')
