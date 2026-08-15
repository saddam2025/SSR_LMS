import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

_RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_ENV = os.getenv("ENV", "development").strip().lower()
if _ENV == "production" and not _RAW_DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required in production; SQLite fallback is disabled.")
DATABASE_URL = _RAW_DATABASE_URL or "sqlite:///./app/data/lms.db"
# A clean source release may not contain runtime data directories.
# Create the parent directory for local SQLite automatically; production should use PostgreSQL.
if DATABASE_URL.startswith("sqlite:///") and not DATABASE_URL.startswith("sqlite:///:memory:"):
    sqlite_path = DATABASE_URL[len("sqlite:///"):]
    if sqlite_path and sqlite_path != ":memory:":
        Path(sqlite_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
# Some managed PostgreSQL providers expose postgres:// or postgresql:// URLs.
# This project installs psycopg v3, so select SQLAlchemy's psycopg dialect explicitly.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine_kwargs = dict(connect_args=connect_args, pool_pre_ping=True, future=True)
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
    )
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_SCHEMA_LOCK_KEY = 1297044308  # stable PostgreSQL advisory-lock key for Mostashar schema bootstrap

def ensure_schema():
    """Create the baseline schema safely when multiple production containers boot together.

    PostgreSQL advisory transaction locking serializes the metadata check/create
    sequence across container instances. SQLite remains unchanged for local/test use.
    """
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.exec_driver_sql(f"SELECT pg_advisory_xact_lock({_SCHEMA_LOCK_KEY})")
            Base.metadata.create_all(bind=conn)
        return
    Base.metadata.create_all(bind=engine)
