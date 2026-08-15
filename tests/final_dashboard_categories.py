import os, re, tempfile
os.environ.setdefault('ENV','development')
os.environ['DATABASE_URL']='sqlite:///' + tempfile.mktemp(suffix='.db')
os.environ['REQUIRE_STAFF_MFA']='false'  # Dashboard regression runs without forcing MFA enrollment.
from fastapi.testclient import TestClient
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run as seed
from app.models import Course, CourseCategory, CourseCategoryAssignment
from app.security import REQUIRE_STAFF_MFA

Base.metadata.drop_all(bind=engine); Base.metadata.create_all(bind=engine); seed()
assert REQUIRE_STAFF_MFA is False
client=TestClient(app)
r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/login',data={'email':'admin@ragab-seddik.local','password':'ChangeMe123!','csrf':csrf},follow_redirects=False)
assert r.status_code==303 and r.headers['location']=='/admin'

for path in ['/admin','/admin/courses','/admin/courses/categories','/admin/courses/categories/add','/dashboard/courses/categories','/dashboard/courses/categories/add']:
    rr=client.get(path,follow_redirects=False)
    assert rr.status_code==200,(path,rr.status_code,rr.text[:200])

rr=client.get('/admin/courses/categories/add')
csrf=re.search(r'name="csrf" value="([^"]+)"',rr.text).group(1)
rr=client.post('/admin/courses/categories',data={
    'name':'الصف الثالث الثانوي - الترم الأول',
    'description':'تنظيم كورسات الصف الثالث',
    'grade':'الصف الثالث الثانوي','sort_order':'1','csrf':csrf
},follow_redirects=False)
assert rr.status_code==303 and rr.headers['location']=='/admin/courses/categories'
rr=client.get('/admin/courses/categories')
assert 'الصف الثالث الثانوي - الترم الأول' in rr.text

with SessionLocal() as db:
    course=db.query(Course).first(); cat=db.query(CourseCategory).first()
    assert course and cat
    course_id,cat_id=course.id,cat.id
rr=client.get('/admin/courses')
csrf=re.search(r'name="csrf" value="([^"]+)"',rr.text).group(1)
rr=client.post(f'/admin/course/{course_id}/category',data={'category_id':cat_id,'csrf':csrf},follow_redirects=False)
assert rr.status_code==303 and rr.headers['location']=='/admin/courses'
with SessionLocal() as db:
    link=db.query(CourseCategoryAssignment).filter_by(course_id=course_id).first()
    assert link and link.category_id==cat_id

base=open('app/templates/base.html',encoding='utf-8').read()
admin_base=open('app/templates/admin_base.html',encoding='utf-8').read()
css=open('app/static/style.css',encoding='utf-8').read()
assert 'family=Cairo' in base and 'family=Cairo' in admin_base
assert 'font-family:"Cairo"' in css
assert '/admin/courses/categories/add' in admin_base
print('FINAL DASHBOARD + CATEGORIES + TYPOGRAPHY + MFA-OFF OK')
