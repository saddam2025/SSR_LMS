"""Production schema validation and performance index guard."""
from sqlalchemy import inspect
from .db import Base, engine
from . import models  # noqa: F401 - registers model metadata

PERFORMANCE_INDEXES = (
    ("ix_users_role_active", "users", "role, is_active"),
    ("ix_active_sessions_user_revoked", "active_sessions", "user_id, revoked_at"),
    ("ix_notifications_user_read", "notifications", "user_id, read_at"),
    ("ix_enrollments_user_active", "enrollments", "user_id, active"),
    ("ix_enrollments_course_active", "enrollments", "course_id, active"),
    ("ix_quiz_attempts_user_status", "quiz_attempts", "user_id, status"),
    ("ix_homework_submissions_student_status", "homework_submissions", "student_id, status"),
    ("ix_subscriptions_user_status", "subscriptions", "user_id, status"),
    ("ix_lesson_progress_user_completed", "lesson_progress", "user_id, completed"),
    ("ix_active_sessions_seen_user", "active_sessions", "last_seen_at, user_id"),
    ("ix_lesson_progress_updated_user", "lesson_progress", "updated_at, user_id"),
    ("ix_quiz_attempts_created_user", "quiz_attempts", "created_at, user_id"),
    ("ix_homework_submissions_submitted_student", "homework_submissions", "submitted_at, student_id"),
    ("ix_attendance_user_date", "student_attendance", "user_id, attendance_date"),
    ("ix_communication_delivery_status_id", "communication_deliveries", "status, id"),
    ("ix_homeworks_course_due", "homeworks", "course_id, due_at"),
)


def validate_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing_tables = []
    missing_columns = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            missing_tables.append(table.name)
            continue
        actual = {c["name"] for c in inspector.get_columns(table.name)}
        expected = {c.name for c in table.columns}
        for name in sorted(expected - actual):
            missing_columns.append(f"{table.name}.{name}")
    if missing_tables or missing_columns:
        details = []
        if missing_tables:
            details.append("missing tables: " + ", ".join(missing_tables[:20]))
        if missing_columns:
            details.append("missing columns: " + ", ".join(missing_columns[:30]))
        raise RuntimeError("Database schema is stale; " + "; ".join(details))


def ensure_performance_indexes() -> None:
    # Run only after schema migration/validation, otherwise an index referencing a
    # newly introduced column can mask the real migration error.
    with engine.begin() as conn:
        for name, table, columns in PERFORMANCE_INDEXES:
            conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})")


def bootstrap_and_validate_schema() -> None:
    # Backward-compatible helper for tests/scripts outside Railway pre-deploy.
    from .db import ensure_schema
    from .schema_migrate import add_missing_columns_safely
    ensure_schema()
    add_missing_columns_safely()
    validate_schema()
    ensure_performance_indexes()
