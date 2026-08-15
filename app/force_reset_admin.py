"""
Run this once against your production DATABASE_URL to guarantee the super_admin
account exists with exactly the email/password/role you want, regardless of
whatever seed.py may or may not have already created.

Usage on Railway:
  1. Make sure DATABASE_URL is already set in the environment (Railway sets this
     automatically if you added the Postgres plugin).
  2. Run as a one-off command in the Railway service shell:
       python -m app.force_reset_admin
     (place this file at app/force_reset_admin.py, next to seed.py)

This clears any account lockout and failed-login counters too, in case that was
the actual cause of "wrong credentials".
"""
import os
from .db import SessionLocal, ensure_schema
from .models import User
from .security import hash_password

NEW_EMAIL = "almostashar9974@gmail.com"
NEW_PASSWORD = "1606160616061606"
NEW_ROLE = "super_admin"


def run():
    ensure_schema()
    db = SessionLocal()
    try:
        email = NEW_EMAIL.strip().lower()
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(name="مدير المنصة", email=email, role=NEW_ROLE)
            db.add(user)
            print(f"Creating new account for {email}")
        else:
            print(f"Found existing account id={user.id} role={user.role} — resetting it")
        user.password_hash = hash_password(NEW_PASSWORD)
        user.role = NEW_ROLE
        user.is_active = True
        user.failed_login_count = 0
        user.locked_until = None
        db.commit()
        print(f"Done. {email} is now role={NEW_ROLE}, active, unlocked, password reset.")
    finally:
        db.close()


if __name__ == "__main__":
    run()