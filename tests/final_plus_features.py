import os,re
from pathlib import Path
DB=os.path.join(os.getenv('TMPDIR','/tmp'),'final_plus_features.db')
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
from app.models import User,Course,ActivationCode,DiscussionPost,PointLedger

def csrf(html):
    m=re.search(r'name="csrf" value="([^"]+)"',html); assert m,html[:800]; return m.group(1)

def login(c,email,pw):
    r=c.get('/login'); t=csrf(r.text)
    r=c.post('/login',data={'email':email,'password':pw,'csrf':t},follow_redirects=True)
    assert r.status_code==200, r.text[:500]
    return r

# Student features
with TestClient(app) as c:
    r=login(c,'student@ragab-seddik.local','Student123!')
    assert 'نقاطي' in r.text and 'خطة اليوم' in r.text
    assert c.get('/study-plan').status_code==200
    assert c.get('/leaderboard').status_code==200
    assert c.get('/search?q=Introduction').status_code==200
    r=c.get('/profile'); t=csrf(r.text)
    r=c.post('/profile',data={'phone':'01000000001','father_phone':'01000000002','mother_phone':'01000000003','school':'Test School','governorate':'القاهرة','grade':'الثالث الثانوي','section':'علمي','parent_job':'Teacher','csrf':t},follow_redirects=True)
    assert r.status_code==200 and 'Test School' in r.text
    db=SessionLocal(); course=db.query(Course).first(); code=ActivationCode(code='PLUS-DEMO',course_id=course.id,max_uses=2,active=True); db.add(code); db.commit(); db.close()
    t=csrf(c.get('/dashboard').text)
    r=c.post('/activate-code',data={'code':'PLUS-DEMO','csrf':t},follow_redirects=False)
    assert r.status_code==303
    db=SessionLocal(); lesson=course=db.query(Course).first(); lesson=db.query(__import__('app.models',fromlist=['Lesson']).Lesson).order_by(__import__('app.models',fromlist=['Lesson']).Lesson.order_index).first(); db.close()
    r=c.get(f'/lesson/{lesson.id}'); t=csrf(r.text)
    r=c.post(f'/lesson/{lesson.id}/discussion',data={'body':'سؤال تجريبي عن الدرس','csrf':t},follow_redirects=True)
    assert r.status_code==200 and 'سؤال تجريبي' in r.text

# OTP local flow
with TestClient(app) as c:
    r=c.get('/otp-login'); t=csrf(r.text)
    r=c.post('/otp-login/request',data={'phone':'01000000001','csrf':t})
    assert r.status_code==200
    m=re.search(r'رمز بيئة التطوير: <b>(\d{6})</b>',r.text); assert m, r.text[:1000]
    code=m.group(1); t=csrf(r.text)
    r=c.post('/otp-login/verify',data={'code':code,'csrf':t},follow_redirects=True)
    assert r.status_code==200 and 'لوحة الطالب' in r.text

# Parent weekly report
with TestClient(app) as c:
    r=login(c,'parent@ragab-seddik.local','Parent12345!')
    db=SessionLocal(); student=db.query(User).filter_by(role='student').first(); db.close()
    r=c.get(f'/parent/report/{student.id}'); assert r.status_code==200 and 'تقرير' in r.text

# Admin commerce and moderation visibility
with TestClient(app) as c:
    r=login(c,'admin@ragab-seddik.local','ChangeMe123!')
    assert c.get('/admin/commerce').status_code==200
    db=SessionLocal(); assert db.query(DiscussionPost).count()>=1; assert db.query(PointLedger).count()>=1; db.close()
print('FINAL PLUS FEATURES TEST OK')
