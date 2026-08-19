from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_direct_r2_upload_is_wired_with_fallback():
    media = (ROOT / "app" / "routers" / "media.py").read_text(encoding="utf-8")
    js = (ROOT / "app" / "static" / "admin-media-upload.js").read_text(encoding="utf-8")
    assert '/media-upload/init' in media
    assert '/media-upload/finalize' in media
    assert 'run_in_threadpool(validate_upload_structure' in media
    assert 'run_in_threadpool(save_upload_file' in media
    assert 'directMediaUpload' in js
    assert 'serverFormUpload' in js


def test_scale_safe_runtime_defaults_are_present():
    start = (ROOT / "container-start.sh").read_text(encoding="utf-8")
    db = (ROOT / "app" / "db.py").read_text(encoding="utf-8")
    context = (ROOT / "app" / "request_context.py").read_text(encoding="utf-8")
    assert 'WEB_CONCURRENCY:-2' in start
    assert 'DB_POOL_SIZE", "5"' in db
    assert 'DB_MAX_OVERFLOW", "5"' in db
    assert 'pool_use_lifo=True' in db
    assert 'SESSION_TOUCH_SECONDS", "180"' in context


def test_large_student_count_hot_paths_are_bounded():
    dashboards = (ROOT / "app" / "routers" / "dashboards.py").read_text(encoding="utf-8")
    admin_users = (ROOT / "app" / "routers" / "admin_users.py").read_text(encoding="utf-8")
    security = (ROOT / "app" / "routers" / "admin_security.py").read_text(encoding="utf-8")
    reports = (ROOT / "app" / "services" / "reports.py").read_text(encoding="utf-8")
    assert 'performance_candidate_student_ids' in dashboards
    assert 'student_ids=[student.id]' in admin_users
    assert 'visible_user_ids' in security
    assert 'def performance_candidate_student_ids' in reports


def test_production_media_requires_durable_storage():
    production = (ROOT / "app" / "production.py").read_text(encoding="utf-8")
    preflight = (ROOT / "app" / "preflight.py").read_text(encoding="utf-8")
    assert 'durable_media_storage' in production
    assert 'verify_storage_roundtrip' in preflight


def test_performance_indexes_are_bootstrapped():
    guard = (ROOT / "app" / "schema_guard.py").read_text(encoding="utf-8")
    for name in (
        'ix_users_role_active', 'ix_active_sessions_user_revoked',
        'ix_notifications_user_read', 'ix_enrollments_user_active',
        'ix_quiz_attempts_user_status',
    ):
        assert name in guard

def test_cross_channel_student_mutations_share_lock_namespaces():
    browser = (ROOT / "app" / "routers" / "learning_runtime.py").read_text(encoding="utf-8")
    api = (ROOT / "app" / "api_v1_learning.py").read_text(encoding="utf-8")
    interactions = (ROOT / "app" / "api_v1_interactions.py").read_text(encoding="utf-8")
    # Browser and separated API must serialize the same logical mutation with the same lock.
    # Start and submit share one lifecycle lock so cross-channel requests cannot overlap.
    assert browser.count('_pg_xact_lock(db, 5507') >= 2 and api.count('_pg_xact_lock(db, 5507') >= 2
    assert '_pg_xact_lock(db, 5509' not in browser and '_pg_xact_lock(db, 5509' not in api
    assert '_pg_xact_lock(db, 5506' in browser and '_pg_xact_lock(db, 5506' in api  # homework submit
    assert '_pg_xact_lock(db, 5508' in browser and '_pg_xact_lock(db, 5508' in interactions  # checkpoint


def test_upload_finalize_is_idempotent_and_stream_mutations_are_serialized():
    media = (ROOT / "app" / "routers" / "media.py").read_text(encoding="utf-8")
    assert '_pg_xact_lock(db, 5530' in media
    assert 'filter_by(storage_key=key).with_for_update().first()' in media
    assert '"idempotent": True' in media
    assert '_pg_xact_lock(db, 5531, lesson.id)' in media
    assert 'processing_status in {"uploading", "processing"}' in media
