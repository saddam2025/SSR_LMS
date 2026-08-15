from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from ..db import get_db
from ..request_context import require_role, template_context as ctx
from ..services.template_rendering import render_template
from ..production import production_status
from ..cache import client as cache_client
router=APIRouter()

@router.get("/admin/system-status", response_class=HTMLResponse)
def admin_system_status(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    status = production_status()
    try:
        db.execute(text("SELECT 1")); status["database_live"] = True
    except Exception:
        status["database_live"] = False
    try:
        c = cache_client(); status["redis_live"] = bool(c and c.ping()) if c else False
    except Exception:
        status["redis_live"] = False
    return render_template("admin_system_status.html", ctx(request, db, status=status))

