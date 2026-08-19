"""Conservative additive schema migration for Railway PostgreSQL upgrades.

SQLAlchemy create_all() creates missing tables but never adds columns to existing
ones. This helper only performs additive column migrations that are safe to infer
from current SQLAlchemy metadata. Destructive/type-changing migrations are never
attempted automatically.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect, literal, text
from sqlalchemy.schema import CreateColumn

from .db import Base, engine
from . import models  # noqa: F401 - register metadata


def _quoted(name: str) -> str:
    return engine.dialect.identifier_preparer.quote(name)


def _scalar_default(column) -> tuple[bool, Any]:
    default = column.default
    if default is None:
        return False, None
    arg = default.arg
    if callable(arg):
        # Timestamp factories are the only callable defaults safe to infer for
        # an existing row. Other application callables require explicit migration.
        type_name = column.type.__class__.__name__.lower()
        if "date" in type_name or "time" in type_name:
            return True, datetime.utcnow()
        return False, None
    return True, arg


def _literal_sql(value: Any) -> str:
    if isinstance(value, datetime):
        return "CURRENT_TIMESTAMP"
    if isinstance(value, date):
        return literal(value).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}).string
    return literal(value).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}).string


def _table_has_rows(conn, table_name: str) -> bool:
    q = f"SELECT 1 FROM {_quoted(table_name)} LIMIT 1"
    return conn.execute(text(q)).first() is not None


def add_missing_columns_safely() -> list[str]:
    """Add safely inferable missing columns and return migration descriptions.

    PostgreSQL production only. SQLite remains a local/test database and is not
    auto-mutated here. A missing NOT NULL column without a safe default on a
    non-empty table raises a precise error instead of corrupting historical rows.
    """
    if engine.dialect.name != "postgresql":
        return []

    migrated: list[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        # Serialize migrations across Railway pre-deploy attempts/replicas.
        conn.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 1297044310})
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # create_all handles missing tables before this helper.
            actual = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in actual:
                    continue
                if column.primary_key:
                    raise RuntimeError(f"Unsafe automatic migration: missing primary key {table.name}.{column.name}")

                has_rows = _table_has_rows(conn, table.name)
                has_default, default_value = _scalar_default(column)
                if not column.nullable and has_rows and not has_default and column.server_default is None:
                    raise RuntimeError(
                        f"Unsafe automatic migration: {table.name}.{column.name} is NOT NULL, table has rows, and no safe default is defined"
                    )

                # Build only the SQL type from current metadata; constraints/default
                # are applied deliberately below to support historical rows safely.
                type_sql = column.type.compile(dialect=engine.dialect)
                ddl = f"ALTER TABLE {_quoted(table.name)} ADD COLUMN {_quoted(column.name)} {type_sql}"

                temporary_default = None
                if column.server_default is not None:
                    # Preserve an explicit server default exactly as compiled by SQLAlchemy.
                    full_col = str(CreateColumn(column).compile(dialect=engine.dialect))
                    # CreateColumn includes the column name/type/default/nullability.
                    ddl = f"ALTER TABLE {_quoted(table.name)} ADD COLUMN {full_col}"
                elif has_default:
                    temporary_default = _literal_sql(default_value)
                    ddl += f" DEFAULT {temporary_default}"
                    if not column.nullable:
                        ddl += " NOT NULL"
                elif not column.nullable and not has_rows:
                    ddl += " NOT NULL"

                conn.exec_driver_sql(ddl)
                migrated.append(f"{table.name}.{column.name}")

                # Python-side defaults are not intended to become permanent DB
                # defaults; drop the temporary backfill default after the ADD.
                if temporary_default is not None:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {_quoted(table.name)} ALTER COLUMN {_quoted(column.name)} DROP DEFAULT"
                    )
    return migrated
