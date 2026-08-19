from pathlib import Path

def test_manual_subscription_student_lookup_is_bounded():
    code = Path("app/routers/commerce.py").read_text(encoding="utf-8")
    assert 'student_q: str = ""' in code
    assert 'student_query.order_by(User.id.desc()).limit(50).all()' in code
    assert 'db.query(User).filter(User.role == "student").order_by(User.name).all()' not in code
