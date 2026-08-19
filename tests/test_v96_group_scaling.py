from pathlib import Path


def test_group_admin_avoids_global_membership_materialization():
    code=Path("app/routers/community.py").read_text(encoding="utf-8")
    service=Path("app/services/community.py").read_text(encoding="utf-8")
    tpl=Path("app/templates/admin_group_detail.html").read_text(encoding="utf-8")
    assert "db.query(StudentGroupMembership).all()" not in code
    assert ".group_by(StudentGroupMembership.group_id)" in code
    assert "member_query.count()" in code
    assert ".limit(50).all()" in code
    assert "existing = {" in service and "Enrollment.user_id.in_(member_ids)" in service
    assert "{{member_total}}" in tpl
