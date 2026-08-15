import os
os.environ.setdefault("ENV","test")
os.environ.setdefault("APP_SECRET","strict-v52-test-secret")
from urllib.parse import urlparse
from app.main import _safe_live_url
from app.services.homepage import safe_reel_url as _safe_reel_url
from fastapi import HTTPException

assert _safe_live_url("https://zoom.us/j/123", "zoom") == "https://zoom.us/j/123"
assert _safe_live_url("https://meet.google.com/abc-defg-hij", "meet").startswith("https://")
for bad, provider in [("http://zoom.us/j/123","zoom"),("javascript:alert(1)","custom"),("https://evil.example/j/1","zoom"),("https://user:pass@zoom.us/j/1","zoom")]:
    try:
        _safe_live_url(bad, provider)
        raise AssertionError((bad, provider))
    except HTTPException:
        pass
assert _safe_reel_url("https://www.youtube.com/shorts/abc").startswith("https://")
try:
    _safe_reel_url("https://youtube.com.evil.example/shorts/abc")
    raise AssertionError("reel host confusion accepted")
except HTTPException:
    pass
print("FINAL STRICT V52 FLOW OK")
