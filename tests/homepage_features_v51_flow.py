import os,tempfile,re
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd); os.unlink(path)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['ENV']='development';os.environ['APP_SECRET']='v51-test-secret';os.environ['PUBLIC_BASE_URL']='http://testserver'
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User, HomepageReel, HomepageHonor, HomepageFeature
from app.security import hash_password

def csrf(text): return re.search(r'name="csrf" value="([^"]+)"', text).group(1)
def login(c,e,p):
    r=c.get('/login'); r=c.post('/login',data={'email':e,'password':p,'csrf':csrf(r.text)},follow_redirects=True); assert r.status_code==200

db=SessionLocal(); a=User(name='Admin V51',email='a51@x.com',password_hash=hash_password('Admin123456'),role='super_admin',is_active=True,mfa_enabled=True);db.add(a);db.commit();db.close()
c=TestClient(app)
# Empty optional modules do not render heavy empty sections; AI remains prominent.
r=c.get('/'); assert r.status_code==200 and 'مساعد المستشار الذكي' in r.text and 'home-ai-fab' in r.text and 'homepage-reels' not in r.text
login(c,'a51@x.com','Admin123456')
r=c.get('/admin/homepage'); assert r.status_code==200 and 'ريلز الواجهة' in r.text and 'أوائل الطلبة' in r.text
x=csrf(r.text)
r=c.post('/admin/homepage/reels',data={'csrf':x,'title':'شرح سريع','url':'https://www.youtube.com/shorts/abc123','caption':'قاعدة في دقيقة','sort_order':'1'},follow_redirects=True);assert r.status_code==200
x=csrf(r.text);r=c.post('/admin/homepage/honors',data={'csrf':x,'student_name':'طالب متفوق','grade':'الصف الثالث الثانوي','rank_label':'الأول','score_text':'99%','note':'ممتاز','sort_order':'1','consent_confirmed':'1'},follow_redirects=True);assert r.status_code==200
r=c.get('/'); assert 'لقطات سريعة ومفيدة' in r.text and 'شرح سريع' in r.text and 'أوائل طلاب المستشار' in r.text and 'طالب متفوق' in r.text
# Unsupported arbitrary host rejected.
r=c.get('/admin/homepage');x=csrf(r.text);bad=c.post('/admin/homepage/reels',data={'csrf':x,'title':'bad','url':'https://evil.example/reel/1','sort_order':'0'},follow_redirects=False);assert bad.status_code==400
# Global toggles hide both sections while AI remains.
r=c.get('/admin/homepage');x=csrf(r.text);r=c.post('/admin/homepage/features',data={'csrf':x},follow_redirects=True);assert r.status_code==200
r=c.get('/'); assert 'لقطات سريعة ومفيدة' not in r.text and 'أوائل طلاب المستشار' not in r.text and 'مساعد المستشار الذكي' in r.text
# Staff login regression: content manager lands through /dashboard, not unauthorized /admin.
db=SessionLocal(); cm=User(name='CM',email='cm51@x.com',password_hash=hash_password('Content123456'),role='content_manager',is_active=True,mfa_enabled=True);db.add(cm);db.commit();db.close()
c2=TestClient(app); lp=c2.get('/login');rr=c2.post('/login',data={'email':'cm51@x.com','password':'Content123456','csrf':csrf(lp.text)},follow_redirects=False);assert rr.status_code==303 and rr.headers['location']=='/teacher'
print('HOMEPAGE FEATURES V51 FLOW OK')
