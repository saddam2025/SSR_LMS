import os
from sqlalchemy import text
from .db import Base, engine, SessionLocal, ensure_schema
from .models import User, Course, Lesson, Enrollment, Quiz, Question, ParentStudent, Homework, StudentProfile, PointLedger
from .security import hash_password


def _required(name: str, local_default: str | None = None) -> str:
    value = os.getenv(name)
    if value:
        return value
    if os.getenv("ENV") == "production" or local_default is None:
        raise RuntimeError(f"Missing required production secret: {name}")
    return local_default



def _normalize_legacy_grades(db):
    old_grade = "الصف الثاني الثانوي"
    new_grade = "الصف الثاني الثانوي عام"
    for table in ("courses", "revision_plans", "course_categories", "student_profiles", "student_groups"):
        db.execute(text(f"UPDATE {table} SET grade = :new_grade WHERE grade = :old_grade"), {"new_grade": new_grade, "old_grade": old_grade})


def run():
    ensure_schema()
    db = SessionLocal()
    try:
        production = os.getenv("ENV") == "production"
        # Several stateless Cloudflare Containers may start together. Serialize
        # production bootstrap so only one instance can create the initial admin
        # at a time; the others re-check after the first transaction commits.
        if production and engine.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 1297044309})
        _normalize_legacy_grades(db)
        admin_email = os.getenv("ADMIN_EMAIL", "almostashar9974@gmail.com").strip().lower()
        admin_role = os.getenv("ADMIN_ROLE", "super_admin").strip().lower()
        if admin_role not in {"super_admin", "admin"}:
            admin_role = "super_admin"
        admin = db.query(User).filter(User.email == admin_email).first()
        if not admin:
            admin = User(
                name=os.getenv("ADMIN_NAME", "مدير المنصة"),
                email=admin_email,
                password_hash=hash_password(_required("ADMIN_PASSWORD", "ChangeMe123!")),
                role=admin_role,
                is_active=True,
            )
            db.add(admin); db.flush()

        # Production starts with the minimum privileged bootstrap account only.
        # Demo accounts/content are opt-in outside production, and are created only for a fresh user database.
        demo = ((not production) or os.getenv("SEED_DEMO_USERS", "false").lower() == "true") and db.query(User).count() == 1
        if demo:
            student = User(
                name="طالب تجريبي",
                email=os.getenv("STUDENT_EMAIL", "student@ragab-seddik.local"),
                password_hash=hash_password(_required("STUDENT_PASSWORD", "Student123!")),
                role="student",
            )
            parent = User(
                name="ولي أمر تجريبي",
                email=os.getenv("PARENT_EMAIL", "parent@ragab-seddik.local"),
                password_hash=hash_password(_required("PARENT_PASSWORD", "Parent12345!")),
                role="parent",
            )
            db.add_all([student, parent]); db.flush()
            db.add(ParentStudent(parent_id=parent.id, student_id=student.id))
            db.add(StudentProfile(user_id=student.id, phone="01000000001", father_phone="01000000002", school="مدرسة تجريبية", governorate="القاهرة", grade="الصف الثالث الثانوي", section="علمي"))
            db.add(PointLedger(user_id=student.id, points=50, reason="رصيد بداية تجريبي", ref_type="seed", ref_id=student.id))
            course = Course(
                title="English Secondary – Demo Course",
                description="كورس تجريبي لإظهار وظائف المنصة.",
                grade="الصف الثالث الثانوي", price=300, published=True, teacher_id=None,
            )
            db.add(course); db.flush()
            db.add_all([
                Lesson(course_id=course.id, title="Lesson 1 – Introduction", body="محتوى الدرس الأول التجريبي.", order_index=1, published=True),
                Lesson(course_id=course.id, title="Lesson 2 – Practice", body="محتوى الدرس الثاني التجريبي.", order_index=2, published=True),
            ])
            db.add(Enrollment(user_id=student.id, course_id=course.id, active=True, progress=25))
            db.add(Homework(course_id=course.id, title="واجب تجريبي", instructions="اكتب إجابة قصيرة على تدريب الدرس الأول.", published=True))
            quiz = Quiz(course_id=course.id, title="اختبار تجريبي", published=True)
            db.add(quiz); db.flush()
            db.add_all([
                Question(quiz_id=quiz.id, text="Choose the correct answer: I ___ a student.", option_a="am", option_b="is", option_c="are", option_d="be", correct="a"),
                Question(quiz_id=quiz.id, text="Choose: She ___ English every day.", option_a="study", option_b="studies", option_c="studying", option_d="studied", correct="b"),
            ])
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    run()