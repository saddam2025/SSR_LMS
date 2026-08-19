from pathlib import Path


def test_attendance_no_longer_materializes_all_students_or_global_activity_map():
    code = Path("app/services/community.py").read_text(encoding="utf-8")
    attendance = code.split("def attendance_page",1)[1].split("def attendance_rows",1)[0]
    assert "db.query(User.id).filter(User.role == \"student\", User.is_active == True).all()" not in attendance
    assert "student_last_activity_map(db, page_ids)" in attendance
    assert ".offset((page - 1) * page_size).limit(page_size).all()" in attendance


def test_lesson_override_student_selector_is_bounded_search():
    code = Path("app/routers/courses.py").read_text(encoding="utf-8")
    assert 'student_q: str = ""' in code
    assert "student_query.order_by(User.name, User.id).limit(50).all()" in code
    html = Path("app/templates/admin_lesson_edit.html").read_text(encoding="utf-8")
    assert 'name="student_q"' in html
    assert "بحد أقصى 50" in html


def test_teacher_assessment_uses_sql_counts_and_bounded_queues():
    code = Path("app/routers/dashboards.py").read_text(encoding="utf-8")
    block = code.split('def teacher_assessment_center',1)[1].split('@router.get("/admin"',1)[0]
    assert ".limit(100).all()" in block
    assert "active_enrollments = db.query(Enrollment).filter(Enrollment.active == True).all()" not in block
    assert "missing_q.count()" in block
