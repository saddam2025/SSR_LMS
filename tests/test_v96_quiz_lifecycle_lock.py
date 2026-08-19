from pathlib import Path


def test_web_and_api_quiz_start_submit_share_one_advisory_lock():
    web=Path("app/routers/learning_runtime.py").read_text(encoding="utf-8")
    api=Path("app/api_v1_learning.py").read_text(encoding="utf-8")
    key='_pg_xact_lock(db, 5507, (int(u.id) * 1000003 + int(quiz_id)))'
    assert web.count(key) >= 2
    assert api.count(key) >= 2
    assert '5509' not in web
    assert '5509' not in api
