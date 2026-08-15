import os
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..cache import client as cache_client
from ..db import get_db
from ..observability import snapshot as metrics_snapshot
from ..request_context import require_role

router = APIRouter(tags=["system"])

def _version():
    try:
        return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return "unknown"


@router.get("/health")
def health():
    return {"status": "ok", "service": "ragab-seddik-lms", "version": _version()}


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    redis_state = "disabled"
    if os.getenv("REDIS_URL", "").strip():
        client = cache_client()
        if not client:
            raise HTTPException(503, "Redis unavailable")
        client.ping()
        redis_state = "ok"
    return {"status": "ready", "database": "ok", "redis": redis_state, "environment": os.getenv("ENV", "development")}


@router.get("/internal/metrics")
def internal_metrics(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return {"routes": metrics_snapshot(), "generated_at": datetime.now(timezone.utc).isoformat()}
