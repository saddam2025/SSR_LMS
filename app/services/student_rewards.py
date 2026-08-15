from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import engine
from ..models import StudentStreak

def _pg_xact_lock(db: Session, namespace: int, entity_id: int):
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :entity)"), {"ns": int(namespace), "entity": int(entity_id) & 0x7FFFFFFF})

def touch_student_streak(db: Session, user_id: int):
    today=datetime.utcnow().date(); _pg_xact_lock(db,5509,user_id)
    row=db.query(StudentStreak).filter_by(user_id=user_id).first()
    if not row:
        row=StudentStreak(user_id=user_id,current_days=1,best_days=1,last_activity_date=today.isoformat()); db.add(row); db.commit(); return row
    if row.last_activity_date==today.isoformat(): return row
    try: last=datetime.fromisoformat(row.last_activity_date).date() if row.last_activity_date else None
    except ValueError: last=None
    row.current_days=row.current_days+1 if last and (today-last).days==1 else 1
    row.best_days=max(row.best_days,row.current_days); row.last_activity_date=today.isoformat(); db.commit(); return row
