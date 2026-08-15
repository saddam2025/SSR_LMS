from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..models import HomepageFeature

SUPPORTED_REEL_HOSTS = {
    "instagram.com", "www.instagram.com",
    "facebook.com", "www.facebook.com", "fb.watch",
    "tiktok.com", "www.tiktok.com",
    "youtube.com", "www.youtube.com", "youtu.be",
}

def feature_enabled(db: Session, key: str, default: bool = True) -> bool:
    row = db.query(HomepageFeature).filter_by(key=key).first()
    return default if row is None else bool(row.enabled)

def safe_reel_url(value: str) -> str:
    clean = value.strip()[:700]
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in SUPPORTED_REEL_HOSTS:
        raise HTTPException(400, "رابط الريل يجب أن يكون HTTPS من Instagram/Facebook/TikTok/YouTube")
    return clean
