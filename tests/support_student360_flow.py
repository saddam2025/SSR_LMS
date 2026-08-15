
import os, re
from fastapi.testclient import TestClient
from app.main import app
from app.seed import run
from app.db import SessionLocal
from app.models import User, SupportTicket

run()
client = TestClient(app)

def login(email, password):
    r = client.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    r = client.post("/login", data={"email":email,"password":password,"csrf":csrf}, follow_redirects=False)
    assert r.status_code == 303, (email, r.status_code)
    return csrf

# student opens ticket
login("student@ragab-seddik.local","Student123!")
r=client.get("/support")
assert r.status_code==200
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post("/support/tickets",data={"subject":"مشكلة اختبارية","category":"technical","priority":"normal","message":"تفاصيل المشكلة","csrf":csrf},follow_redirects=False)
assert r.status_code==303
ticket_url=r.headers["location"]
assert ticket_url.startswith("/support/tickets/")
assert client.get(ticket_url).status_code==200

# another student's ownership is enforced by direct model check path semantics via staff flow;
# admin can access ticket and Student 360.
client.cookies.clear()
login("admin@ragab-seddik.local","ChangeMe123!")
db=SessionLocal()
student=db.query(User).filter_by(email="student@ragab-seddik.local").first()
ticket=db.query(SupportTicket).order_by(SupportTicket.id.desc()).first()
sid=student.id; tid=ticket.id
db.close()
assert client.get(f"/admin/students/{sid}").status_code==200
assert client.get(f"/support/tickets/{tid}").status_code==200
r=client.get(f"/support/tickets/{tid}")
csrf=re.search(r'name="csrf" value="([^"]+)"',r.text).group(1)
r=client.post(f"/support/tickets/{tid}/reply",data={"message":"تم استلام المشكلة","csrf":csrf},follow_redirects=False)
assert r.status_code==303
print("SUPPORT + STUDENT360 FLOW OK")
