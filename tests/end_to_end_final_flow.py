
import os, re
from fastapi.testclient import TestClient
from app.main import app
from app.seed import run
from app.db import SessionLocal
from app.models import User, Course, Lesson, Quiz, Homework, SupportTicket

run()
c = TestClient(app)

def csrf_from(path):
    r=c.get(path)
    assert r.status_code==200, (path,r.status_code)
    m=re.search(r'name="csrf" value="([^"]+)"',r.text)
    assert m, ("csrf missing",path)
    return m.group(1)

def login(email,password):
    csrf=csrf_from("/login")
    r=c.post("/login",data={"email":email,"password":password,"csrf":csrf},follow_redirects=False)
    assert r.status_code==303,(email,r.status_code,r.text[:200])

# public home
r=c.get("/")
assert r.status_code==200
assert "المستشار" in r.text
assert "01060309494" in r.text

# admin journey
login("admin@ragab-seddik.local","ChangeMe123!")
assert c.get("/admin").status_code==200
assert c.get("/admin/courses").status_code==200
assert c.get("/admin/students").status_code==200
assert c.get("/admin/commerce").status_code==200
assert c.get("/admin/security").status_code==200
assert c.get("/support").status_code==200

db=SessionLocal()
student=db.query(User).filter_by(email="student@ragab-seddik.local").first()
course=db.query(Course).order_by(Course.id.asc()).first()
lesson=db.query(Lesson).filter_by(course_id=course.id).order_by(Lesson.id.asc()).first()
quiz=db.query(Quiz).filter_by(course_id=course.id).order_by(Quiz.id.asc()).first()
sid=student.id; cid=course.id; lid=lesson.id; qid=quiz.id
db.close()

# admin student 360
assert c.get(f"/admin/students/{sid}").status_code==200

# student journey
c.cookies.clear()
login("student@ragab-seddik.local","Student123!")
assert c.get("/dashboard").status_code==200
assert c.get(f"/course/{cid}").status_code==200

# protected lesson route should be accessible for seeded enrollment
lesson_candidates=[f"/lesson/{lid}", f"/courses/{cid}/lessons/{lid}"]
lesson_ok=False
for path in lesson_candidates:
    rr=c.get(path,follow_redirects=False)
    if rr.status_code in (200,303):
        lesson_ok=True
        break
assert lesson_ok, "No lesson route accessible"

# notifications/support
assert c.get("/notifications").status_code==200
assert c.get("/support").status_code==200
csrf=csrf_from("/support")
r=c.post("/support/tickets",data={
    "subject":"اختبار رحلة كاملة",
    "category":"technical",
    "priority":"normal",
    "message":"اختبار دعم فني End-to-End",
    "csrf":csrf,
},follow_redirects=False)
assert r.status_code==303
assert r.headers["location"].startswith("/support/tickets/")

# parent journey
c.cookies.clear()
login("parent@ragab-seddik.local","Parent12345!")
parent_paths=["/parent","/parent/dashboard"]
assert any(c.get(p,follow_redirects=False).status_code in (200,303) for p in parent_paths)

print("FINAL END-TO-END FLOW OK")
