from pathlib import Path

def test_admin_users_is_bounded_and_searchable():
    code = Path("app/routers/admin_users.py").read_text(encoding="utf-8")
    assert 'page_size = 100' in code
    assert '.offset((page - 1) * page_size).limit(page_size).all()' in code
    assert 'return query.order_by(User.id.desc()).limit(50).all()' in code
    assert 'db.query(ParentStudent).all()' not in code

def test_student_import_does_not_block_async_event_loop():
    code = Path("app/routers/admin_users.py").read_text(encoding="utf-8")
    assert 'def admin_students_import' in code
    assert 'async def admin_students_import' not in code
