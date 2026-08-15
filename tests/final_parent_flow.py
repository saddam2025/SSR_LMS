import os, re
from pathlib import Path
DB=os.path.join(os.getenv('TMPDIR','/tmp'),'final_parent_flow.db')
try: os.remove(DB)
except FileNotFoundError: pass
os.environ['DATABASE_URL']='sqlite:///'+DB
os.environ['ENV']='development'
os.environ['SEED_DEMO_USERS']='true'
from fastapi.testclient import TestClient
from app.seed import run
run()
from app.main import app
from app.db import SessionLocal
from app.models import User, Course, Lesson, Homework, HomeworkSubmission, LessonProgress

def csrf(html):
    m=re.search(r'name="csrf" value="([^"]+)"', html)
    assert m, html[:500]
    return m.group(1)

with TestClient(app) as c:
    r=c.get('/login'); token=csrf(r.text)
    r=c.post('/login', data={'email':'parent@ragab-seddik.local','password':'Parent12345!','csrf':token}, follow_redirects=True)
    assert r.status_code==200 and 'متابعة الأبناء' in r.text and 'طالب تجريبي' in r.text

with TestClient(app) as c:
    r=c.get('/login'); token=csrf(r.text)
    r=c.post('/login', data={'email':'student@ragab-seddik.local','password':'Student123!','csrf':token}, follow_redirects=True)
    assert r.status_code==200
    db=SessionLocal(); course=db.query(Course).first(); lessons=db.query(Lesson).order_by(Lesson.order_index).all(); hw=db.query(Homework).first(); db.close()
    r=c.get(f'/course/{course.id}')
    assert r.status_code==200 and 'مسار التعلم' in r.text and 'الواجبات' in r.text
    r=c.get(f'/lesson/{lessons[1].id}')
    assert r.status_code==403
    db=SessionLocal(); db.add(LessonProgress(user_id=db.query(User).filter_by(role='student').first().id, lesson_id=lessons[0].id, completed=True, watched_seconds=600)); db.commit(); db.close()
    r=c.get(f'/lesson/{lessons[1].id}')
    assert r.status_code==200
    r=c.get(f'/homework/{hw.id}'); token=csrf(r.text)
    r=c.post(f'/homework/{hw.id}', data={'answer_text':'My answer','csrf':token}, follow_redirects=True)
    assert r.status_code==200 and 'My answer' in r.text
print('FINAL PARENT / HOMEWORK / PROGRESSION TEST OK')
