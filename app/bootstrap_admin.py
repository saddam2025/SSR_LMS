"""Idempotent production administrator bootstrap.

Creates only the initial privileged account when the configured ADMIN_EMAIL does
not exist. It never seeds demo students/content and never overwrites an existing
administrator password, so normal restarts are safe.
"""
import os
from sqlalchemy import func, text
from .db import SessionLocal, engine, ensure_schema
from .models import User
from .security import hash_password


def run() -> None:
    if os.getenv("ENV", "development").strip().lower() != "production":
        return
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD", "")
    name = os.getenv("ADMIN_NAME", "مدير منصة المستشار").strip() or "مدير منصة المستشار"
    if not email or "@" not in email:
        raise RuntimeError("ADMIN_EMAIL is required for production admin bootstrap")
    if len(password) < 14:
        raise RuntimeError("ADMIN_PASSWORD must be at least 14 characters for initial bootstrap")
    ensure_schema()
    db = SessionLocal()
    try:
        # Serialize first-admin creation across concurrent Railway containers.
        if engine.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 1297044309})
        existing = db.query(User).filter(func.lower(User.email) == email).first()
        if existing:
            if existing.role not in {"admin", "super_admin"}:
                raise RuntimeError("ADMIN_EMAIL already belongs to a non-admin account")
            if not existing.is_active:
                raise RuntimeError("Configured production admin account is inactive")
            return
        db.add(User(name=name[:120], email=email, password_hash=hash_password(password), role="admin", is_active=True))
        db.commit()
        print("MOSTASHAR ADMIN BOOTSTRAP: initial admin created")
    finally:
        db.close()


if __name__ == "__main__":
    run()
