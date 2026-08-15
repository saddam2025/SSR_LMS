import os,tempfile,re
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v28-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,ContentUnit,QuestionBankItem,QuestionBankTaxonomy,MockExamProfile,Question,Enrollment,Quiz
from app.security import hash_password

def login(client,email,password):
    r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=True); assert r.status_code==200

def csrf_from(client,url):
    r=client.get(url); assert r.status_code==200, r.text[:300]
    m=re.search(r'name="csrf" value="([^"]+)"',r.text); assert m
    return m.group(1),r

db=SessionLocal()
a=User(name='Admin V28',email='admin-v28@example.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True)
s=User(name='Student V28',email='student-v28@example.com',password_hash=hash_password('Student123456'),role='student',is_active=True)
db.add_all([a,s]);db.commit();db.refresh(a);db.refresh(s)
c=Course(title='V28 Mock Course',grade='الصف الثالث الثانوي',published=True,teacher_id=a.id);db.add(c);db.commit();db.refresh(c)
u1=ContentUnit(course_id=c.id,name='Unit 1',order_index=1,published=True);u2=ContentUnit(course_id=c.id,name='Unit 2',order_index=2,published=True);db.add_all([u1,u2]);db.commit();db.refresh(u1);db.refresh(u2)
for i in range(12):
    item=QuestionBankItem(course_id=c.id,created_by=a.id,text=f'Question {i+1}',option_a='Right',option_b='Wrong B',option_c='Wrong C',option_d='Wrong D',correct='A',default_points=1);db.add(item);db.flush()
    db.add(QuestionBankTaxonomy(bank_item_id=item.id,unit_id=u1.id if i<6 else u2.id,difficulty='easy' if i%3==0 else ('hard' if i%3==1 else 'medium')))
db.add(Enrollment(user_id=s.id,course_id=c.id,active=True));db.commit();cid=c.id;sid=s.id;db.close()
admin=TestClient(app);login(admin,'admin-v28@example.com','Admin123456')
csrf,r=csrf_from(admin,'/teacher/mock-exams'); assert 'الامتحانات التجريبية' in r.text
r=admin.post('/teacher/mock-exams',data={'course_id':cid,'title':'Mock V28','question_count':9,'time_limit_minutes':45,'unit_id':0,'difficulty':'all','csrf':csrf},follow_redirects=False);assert r.status_code==303,r.text

db=SessionLocal();p=db.query(MockExamProfile).first();assert p and p.requested_questions==9;qz=db.get(Quiz,p.quiz_id);qid=qz.id;assert db.query(Question).filter_by(quiz_id=qid).count()==9;db.close()
csrf,_=csrf_from(admin,f'/admin/quiz/{qid}');r=admin.post(f'/admin/quiz/{qid}/toggle',data={'csrf':csrf},follow_redirects=False);assert r.status_code==303
student=TestClient(app);login(student,'student-v28@example.com','Student123456')
csrf,r=csrf_from(student,f'/quiz/{qid}'); assert 'Mock V28' in r.text
# submit mostly correct with two wrong to produce mixed analysis
_db=SessionLocal();qs=_db.query(Question).filter_by(quiz_id=qid).all();_db.close()
data={'csrf':csrf}
for idx,q in enumerate(qs): data[f'q_{q.id}']='B' if idx<2 else 'A'
r=student.post(f'/quiz/{qid}',data=data,follow_redirects=True);assert r.status_code==200
assert 'نقاط القوة والضعف' in r.text and 'حسب الوحدة' in r.text and 'حسب الصعوبة' in r.text
print('MOCK EXAM V28 FLOW OK')
