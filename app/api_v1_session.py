from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .db import get_db
from .security import ensure_csrf, check_csrf
from .api_v1_common import user

router = APIRouter(tags=["api-v1-session"])

@router.get('/session')
def session_info(request: Request, db: Session = Depends(get_db)):
    resolved = user(request, db)
    return {'data': {
        'id': resolved.id,
        'name': resolved.name,
        'role': resolved.role,
        'csrf': ensure_csrf(request.session),
    }}

@router.post('/logout')
def api_logout(request: Request, db: Session = Depends(get_db)):
    user(request, db)
    token = request.headers.get('x-csrf-token', '')
    if not check_csrf(request.session, token):
        raise HTTPException(403, 'CSRF failed')
    rec = getattr(request.state, '_lms_session_record', None)
    if rec is not None and not rec.revoked_at:
        rec.revoked_at = datetime.utcnow()
        db.commit()
    request.session.clear()
    return {'data': {'logged_out': True}}
