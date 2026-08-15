from fastapi import HTTPException, Request
from sqlalchemy.orm import Session


def user(request: Request, db: Session):
    resolver = getattr(request.app.state, "resolve_user", None)
    resolved = resolver(request, db) if resolver else None
    if not resolved:
        raise HTTPException(401, "Authentication required")
    return resolved
