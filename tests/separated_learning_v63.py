import os,tempfile,sys
from pathlib import Path
fd,path=tempfile.mkstemp(suffix='.db');os.close(fd)
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v63-learning-secret-'+'x'*80
os.environ['SESSION_SECRET']='v63-session-secret-'+'y'*80
os.environ['REQUIRE_STAFF_MFA']='false'
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.models import User,Course,Lesson,Enrollment,Quiz,Question,Homework,Notification,HomeworkSubmission,QuizAttempt
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal();u=User(name='Student V63',email='v63@example.com',password_hash=hash_password('StudentPass12345'),role='student',is_active=True);c=Course(title='English V63',description='Grammar',grade='الصف الثاني الثانوي عام',published=True);db.add_all([u,c]);db.flush();l=Lesson(course_id=c.id,title='Future Tense',body='will and going to',published=True,order_index=1);db.add(l);db.flush();db.add(Enrollment(user_id=u.id,course_id=c.id,active=True));q=Quiz(course_id=c.id,title='Future Quiz',published=True,time_limit_minutes=30,max_attempts=2,shuffle_questions=False);db.add(q);db.flush();db.add(Question(quiz_id=q.id,text='Choose future form',option_a='will',option_b='did',option_c='was',option_d='had',correct='A'));h=Homework(course_id=c.id,lesson_id=l.id,title='Future Homework',instructions='Write 3 sentences',published=True);db.add(h);db.add(Notification(user_id=u.id,title='Welcome',body='Start now'));db.commit();qid=q.id;hid=h.id;db.close()
cl=TestClient(app);csrf=cl.get('/login').text.split('name="csrf" value="',1)[1].split('"',1)[0];r=cl.post('/login',data={'email':'v63@example.com','password':'StudentPass12345','csrf':csrf},follow_redirects=False);assert r.status_code==303
sess=cl.get('/api/v1/session').json()['data'];token=sess['csrf']
r=cl.get('/api/v1/learning-center');assert r.status_code==200,r.text;assert len(r.json()['data']['quizzes'])==1 and len(r.json()['data']['homeworks'])==1
r=cl.get(f'/api/v1/quizzes/{qid}/attempt');assert r.status_code==200,r.text;qd=r.json()['data'];assert 'correct' not in qd['questions'][0] and qd['questions'][0]['options']['A']=='will'
r=cl.post(f'/api/v1/quizzes/{qid}/submit',json={'answers':{str(qd['questions'][0]['id']):'A'}});assert r.status_code==403
r=cl.post(f'/api/v1/quizzes/{qid}/submit',json={'answers':{str(qd['questions'][0]['id']):'A'}},headers={'X-CSRF-Token':token});assert r.status_code==200,r.text;assert r.json()['data']['percentage']==100.0
r=cl.get(f'/api/v1/homeworks/{hid}');assert r.status_code==200
r=cl.post(f'/api/v1/homeworks/{hid}/submit',json={'answer_text':'I will study.'},headers={'X-CSRF-Token':token});assert r.status_code==200,r.text
db=SessionLocal();assert db.query(HomeworkSubmission).count()==1 and db.query(QuizAttempt).filter_by(status='submitted').count()==1;db.close()
r=cl.get('/api/v1/search?q=Future');assert r.status_code==200 and len(r.json()['data']['lessons'])==1
r=cl.get('/api/v1/study-plan');assert r.status_code==200 and isinstance(r.json()['data']['tasks'],list)
r=cl.post('/api/v1/notifications/read-all');assert r.status_code==403
r=cl.post('/api/v1/notifications/read-all',headers={'X-CSRF-Token':token});assert r.status_code==200
js=Path('frontend/assets/app.js').read_text();router=Path('app/api_v1.py').read_text()
for needle in ['bootLearning','bootQuiz','bootHomework','/api/v1/learning-center','/api/v1/study-plan'] : assert needle in js
assert 'learning_router' in router
for page in ['learning.html','quiz.html','homework.html']: assert Path('frontend/student/'+page).exists()
print('V63 SEPARATED LEARNING CENTER CONTRACT OK')
