import os,tempfile,re
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v27-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User,Course,Lesson,Quiz,Homework,StudentProfile,RevisionPlan,RevisionTask,RevisionTaskProgress
from app.security import hash_password

def login(client,email,password):
    r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
    r=client.post('/login',data={'email':email,'password':password,'csrf':csrf},follow_redirects=True); assert r.status_code==200

def csrf_from(client,url):
    r=client.get(url); assert r.status_code==200, r.text[:200]
    m=re.search(r'name="csrf" value="([^"]+)"',r.text); assert m
    return m.group(1),r

db=SessionLocal()
a=User(name='Admin V27',email='admin-v27@example.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True)
s=User(name='طالب V27',email='student-v27@example.com',password_hash=hash_password('Student123456'),role='student',is_active=True)
db.add_all([a,s]);db.commit();db.refresh(a);db.refresh(s)
db.add(StudentProfile(user_id=s.id,grade='الصف الثالث الثانوي'))
c=Course(title='V27 Review Course',grade='الصف الثالث الثانوي',published=True,teacher_id=a.id);db.add(c);db.commit();db.refresh(c)
l=Lesson(course_id=c.id,title='Revision Lesson',published=True,order_index=1);q=Quiz(course_id=c.id,title='Revision Quiz',published=True);h=Homework(course_id=c.id,title='Revision HW',published=True);db.add_all([l,q,h]);db.commit();lid=l.id;qid=q.id;hid=h.id;sid=s.id;db.close()
admin=TestClient(app);login(admin,'admin-v27@example.com','Admin123456')
csrf,r=csrf_from(admin,'/teacher/revision'); assert 'خطط المراجعات النهائية' in r.text
r=admin.post('/teacher/revision/plan',data={'title':'خطة الثانوية العامة','description':'7 أيام مراجعة','grade':'الصف الثالث الثانوي','start_date':'2026-08-13','exam_date':'2026-08-20','csrf':csrf},follow_redirects=False); assert r.status_code==303

db=SessionLocal();plan=db.query(RevisionPlan).first();pid=plan.id;db.close()
csrf,_=csrf_from(admin,'/teacher/revision')
for day,title,ctype,cid in [(1,'راجع الدرس','lesson',lid),(2,'اختبر نفسك','quiz',qid),(3,'حل الواجب','homework',hid),(4,'راجع ملاحظاتك','note',0)]:
    r=admin.post('/teacher/revision/task',data={'plan_id':pid,'day_number':day,'order_index':1,'title':title,'description':'مهمة اليوم','content_type':ctype,'content_id':cid,'due_at':'','csrf':csrf},follow_redirects=False); assert r.status_code==303
csrf,_=csrf_from(admin,'/teacher/revision'); r=admin.post(f'/teacher/revision/plan/{pid}/toggle',data={'csrf':csrf},follow_redirects=False);assert r.status_code==303
student=TestClient(app);login(student,'student-v27@example.com','Student123456')
csrf,r=csrf_from(student,'/revision'); assert 'خطة الثانوية العامة' in r.text and 'راجع الدرس' in r.text and 'اختبر نفسك' in r.text
# complete first task
db=SessionLocal();task=db.query(RevisionTask).filter_by(plan_id=pid).order_by(RevisionTask.day_number).first();tid=task.id;db.close()
r=student.post(f'/revision/task/{tid}/toggle',data={'csrf':csrf},follow_redirects=True); assert r.status_code==200 and '25%' in r.text
# toggle back
a=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1);r=student.post(f'/revision/task/{tid}/toggle',data={'csrf':a},follow_redirects=True);assert r.status_code==200 and '0%' in r.text
print('REVISION PLAN V27 FLOW OK')
