import os,re,tempfile
os.environ.setdefault('ENV','development'); os.environ['DATABASE_URL']='sqlite:///'+tempfile.mktemp(suffix='.db')
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base,engine,SessionLocal
from app.seed import run as seed
from app.models import Course,Quiz,Question,QuestionBankItem,QuizQuestionSetting
Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()
def login(c):
 r=c.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=c.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False); assert r.status_code==303
c=TestClient(app); login(c); db=SessionLocal(); course=db.query(Course).first(); qz=Quiz(course_id=course.id,title='V11 Test',published=False,time_limit_minutes=20,max_attempts=2); db.add(qz); db.commit(); qid=qz.id; db.close()
r=c.get(f'/admin/quiz/{qid}'); assert r.status_code==200; csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=c.post(f'/admin/quiz/{qid}/bank',data={'text':'Choose the correct answer','option_a':'A1','option_b':'B1','option_c':'C1','option_d':'D1','correct':'B','points':'3','csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); item=db.query(QuestionBankItem).first(); bid=item.id; db.close()
r=c.get(f'/admin/quiz/{qid}'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=c.post(f'/admin/quiz/{qid}/bank/{bid}/use',data={'csrf':csrf},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); q=db.query(Question).filter_by(quiz_id=qid).first(); meta=db.query(QuizQuestionSetting).filter_by(question_id=q.id).first(); assert meta.points==3; question_id=q.id; db.close()
r=c.get(f'/admin/quiz/{qid}'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1); r=c.post(f'/admin/question/{question_id}/meta',data={'position':'2','points':'5','csrf':csrf},follow_redirects=False); assert r.status_code==303
r=c.get(f'/admin/quiz/{qid}/preview'); assert r.status_code==200 and 'معاينة قبل النشر' in r.text and '5 درجة' in r.text
print('QUIZ AUTHORING V11 FLOW OK')
