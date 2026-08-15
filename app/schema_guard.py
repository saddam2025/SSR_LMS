"""Small production schema guard for deployments that still use SQLAlchemy create_all.

It detects missing model tables/columns after bootstrap. It is intentionally not a
replacement for full migrations, but prevents starting against an obviously stale DB.
"""
from sqlalchemy import inspect
from .db import Base, engine, ensure_schema
from . import models  # noqa: F401 - registers model metadata


def bootstrap_and_validate_schema() -> None:
    ensure_schema()
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
