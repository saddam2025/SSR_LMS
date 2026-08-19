from pathlib import Path


def test_live_class_admin_is_paginated_and_set_based():
    router = Path("app/routers/community.py").read_text(encoding="utf-8")
    service = Path("app/services/community.py").read_text(encoding="utf-8")
    template = Path("app/templates/admin_live_class_detail.html").read_text(encoding="utf-8")
    assert "live_class_student_query(db,item).filter(User.id==student_id)" in router
    assert "live_class_student_ids(db, item)" in router
    assert "page_size=100" in router
    assert ".offset((page - 1) * page_size).limit(page_size)" in service
    assert "إجمالي الطلاب: {{total}}" in template
    assert "recipient_ids = live_class_student_ids(db, item)" in router
