import os, re, tempfile
os.environ.setdefault("ENV", "development")
os.environ.setdefault("DATABASE_URL", "sqlite:///./release_audit.db")
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas
from app.main import app
from app.db import Base, engine, SessionLocal
from app.seed import run
from app.models import Course, Lesson, Quiz
from app.watermark import watermark_pdf

Base.metadata.drop_all(engine); Base.metadata.create_all(engine); run()
# Compile every UI template.
env = Environment(loader=FileSystemLoader("app/templates"))
for p in Path("app/templates").glob("*.html"):
    env.get_template(p.name)

def login(email, password):
    c = TestClient(app)
    r = c.get("/login")
    csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
    r = c.post("/login", data={"email": email, "password": password, "csrf": csrf}, follow_redirects=False)
    assert r.status_code == 303
    return c

db = SessionLocal(); course = db.query(Course).first(); lesson = db.query(Lesson).first(); quiz = db.query(Quiz).first(); db.close()
admin = login("admin@ragab-seddik.local", "ChangeMe123!")
for path in ["/admin", "/admin/users", "/admin/students", "/admin/security", "/admin/commerce", f"/admin/course/{course.id}", f"/admin/quiz/{quiz.id}", "/account/security"]:
    assert admin.get(path, follow_redirects=True).status_code == 200, path
student = login("student@ragab-seddik.local", "Student123!")
for path in ["/dashboard", f"/course/{course.id}", f"/lesson/{lesson.id}", f"/quiz/{quiz.id}"]:
    assert student.get(path, follow_redirects=True).status_code == 200, path
assert student.get("/admin", follow_redirects=False).status_code == 303
# Legacy teacher route must not expose a teacher dashboard to students.
assert student.get("/teacher", follow_redirects=False).status_code == 303
# Dynamic PDF watermark smoke check.
fd, src = tempfile.mkstemp(suffix=".pdf"); os.close(fd)
c = canvas.Canvas(src); c.drawString(72, 720, "release audit"); c.save()
out = watermark_pdf(Path(src).read_bytes(), "Student ID 3 | audit@example.com")
assert out.startswith(b"%PDF-") and len(out) > len(Path(src).read_bytes())
Path(src).unlink(missing_ok=True)
print("RELEASE AUDIT TEST OK")
