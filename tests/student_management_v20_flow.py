import os,tempfile,re,io
from openpyxl import Workbook
fd,path=tempfile.mkstemp(suffix='.db'); os.close(fd)
os.environ['DATABASE_URL']='sqlite:///'+path
os.environ['APP_SECRET']='v20-test-secret-long-enough-123456789'
os.environ['ENV']='test'
from fastapi.testclient import TestClient
from app.db import Base,engine,SessionLocal
from app.main import app
from app.models import User,Course,StudentGroup,StudentGroupMembership,Enrollment,Notification,CommunicationCampaign
from app.security import hash_password
Base.metadata.create_all(bind=engine)
db=SessionLocal()
admin=User(name='Admin',email='admin@test.local',password_hash=hash_password('AdminPass12345'),role='super_admin',is_active=True,mfa_enabled=True)
g=StudentGroup(name='3A',grade='3rd',active=True)
c=Course(title='English 3',grade='3rd',published=True)
db.add_all([admin,g,c]); db.commit(); gid=g.id; cid=c.id; db.close()
client=TestClient(app)
r=client.get('/login'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/login',data={'email':'admin@test.local','password':'AdminPass12345','csrf':csrf},follow_redirects=True); assert r.status_code==200
r=client.get('/admin/students'); assert r.status_code==200 and 'مركز إدارة الطلاب المتقدم' in r.text
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
# CSV import
csv_data='name,email,phone,grade,school\nStudent One,s1@test.local,01000000001,3rd,School A\nStudent Two,s2@test.local,01000000002,3rd,School B\n'.encode()
r=client.post('/admin/students/import',data={'csrf':csrf,'default_password':'StudentPass12345','group_id':gid,'course_id':cid},files={'file':('students.csv',csv_data,'text/csv')},follow_redirects=False); assert r.status_code==303
# XLSX import + update existing row
wb=Workbook(); ws=wb.active; ws.append(['name','email','phone','grade','school']); ws.append(['Student One Updated','s1@test.local','01099999999','3rd','School A']); ws.append(['Student Three','s3@test.local','01000000003','3rd','School C']); bio=io.BytesIO(); wb.save(bio)
r=client.get('/admin/students'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/admin/students/import',data={'csrf':csrf,'default_password':'StudentPass12345','group_id':gid,'course_id':cid},files={'file':('students.xlsx',bio.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},follow_redirects=False); assert r.status_code==303
db=SessionLocal(); students=db.query(User).filter_by(role='student').order_by(User.id).all(); assert len(students)==3; assert db.query(User).filter_by(email='s1@test.local').one().name=='Student One Updated'; assert db.query(StudentGroupMembership).count()==3; assert db.query(Enrollment).filter_by(course_id=cid,active=True).count()==3; ids=[x.id for x in students]; db.close()
# Bulk notification to two selected students
r=client.get('/admin/students'); csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post('/admin/students/bulk',data={'csrf':csrf,'action':'notify','student_ids':[str(ids[0]),str(ids[1])],'group_id':'0','course_id':'0','title':'Bulk test','body':'Hello students'},follow_redirects=False); print('bulk status',r.status_code,r.text[:500]); assert r.status_code==303
db=SessionLocal(); assert db.query(Notification).filter(Notification.title=='Bulk test').count()==2; assert db.query(CommunicationCampaign).filter_by(audience_type='selected_students').count()==1; db.close()
print('STUDENT MANAGEMENT V20 FLOW OK')
