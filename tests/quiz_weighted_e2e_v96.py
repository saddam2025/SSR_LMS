import os
import re

os.environ['DATABASE_URL'] = 'sqlite:///./quiz_weighted_e2e_v96.db'
os.environ['ENV'] = 'test'
os.environ['APP_SECRET'] = 'weighted-e2e-test-secret'

from fastapi.testclient import TestClient
from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import Course, Enrollment, PointLedger, Question, Quiz, QuizAttempt, QuizQuestionSetting, User
from app.seed import run as seed

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)
seed()

db = SessionLocal()
student = db.query(User).filter_by(role='student').first()
course = db.query(Course).first()
assert student and course
if not db.query(Enrollment).filter_by(user_id=student.id, course_id=course.id).first():
    db.add(Enrollment(user_id=student.id, course_id=course.id, active=True))
qz = Quiz(course_id=course.id, title='Weighted E2E', published=True, time_limit_minutes=20, max_attempts=1, shuffle_questions=False)
db.add(qz); db.flush()
questions = [
    Question(quiz_id=qz.id, text='W1', option_a='a', option_b='b', option_c='c', option_d='d', correct='A'),
    Question(quiz_id=qz.id, text='W2', option_a='a', option_b='b', option_c='c', option_d='d', correct='B'),
    Question(quiz_id=qz.id, text='W3', option_a='a', option_b='b', option_c='c', option_d='d', correct='C'),
]
db.add_all(questions); db.flush()
for pos, (q, points) in enumerate(zip(questions, (2, 3, 5)), 1):
    db.add(QuizQuestionSetting(question_id=q.id, position=pos, points=points))
db.commit(); quiz_id=qz.id; student_email=student.email; question_ids=[q.id for q in questions]; db.close()

client = TestClient(app)
r = client.get('/login')
csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
r = client.post('/login', data={'email': student_email, 'password':'Student123!', 'csrf':csrf}, follow_redirects=False)
assert r.status_code in (302,303), r.text
r = client.get(f'/quiz/{quiz_id}')
assert r.status_code == 200, r.text
csrf = re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)
answers = {
    'csrf': csrf,
    f'q_{question_ids[0]}': 'A',  # +2
    f'q_{question_ids[1]}': 'A',  # +0
    f'q_{question_ids[2]}': 'C',  # +5
}
r = client.post(f'/quiz/{quiz_id}', data=answers)
assert r.status_code == 200, r.text

db = SessionLocal()
attempt = db.query(QuizAttempt).filter_by(user_id=student.id, quiz_id=quiz_id).one()
assert attempt.status == 'submitted'
assert attempt.score == 7, attempt.score
assert attempt.total == 10, attempt.total
ledger_count = db.query(PointLedger).filter_by(user_id=student.id, ref_type='quiz_attempt', ref_id=attempt.id).count()
assert ledger_count == 1, ledger_count
db.close()

# Replaying the same form after submission must not score or award twice.
r2 = client.post(f'/quiz/{quiz_id}', data=answers)
assert r2.status_code == 409, r2.status_code
db = SessionLocal()
ledger_count = db.query(PointLedger).filter_by(user_id=student.id, ref_type='quiz_attempt', ref_id=attempt.id).count()
assert ledger_count == 1, ledger_count
db.close()
print('WEIGHTED QUIZ E2E V96 OK: 7/10 + duplicate submit blocked')
