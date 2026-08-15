from app.seed import run
from app.db import SessionLocal
from app.models import User, Course, Lesson, Quiz
run()
db = SessionLocal()
assert db.query(User).count() >= 3
assert db.query(Course).count() >= 1
assert db.query(Lesson).count() >= 2
assert db.query(Quiz).count() >= 1
print("SMOKE TEST OK")
db.close()
