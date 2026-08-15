import os
from pathlib import Path
import pytest
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[1]

def test_missing_video_allowlist_is_not_500(monkeypatch):
    monkeypatch.setenv("ENV","production")
    monkeypatch.delenv("VIDEO_ALLOWED_HOSTS",raising=False)
    from app.services.courses import validated_video_url
    with pytest.raises(HTTPException) as e:
        validated_video_url("https://example.com/video")
    assert e.value.status_code == 503
    assert "VIDEO_ALLOWED_HOSTS" in str(e.value.detail)

def test_upload_diagnostics_present():
    main=(ROOT/"app"/"main.py").read_text(encoding="utf-8")
    courses=(ROOT/"app"/"routers"/"courses.py").read_text(encoding="utf-8")
    assert "Request ID:" in main
    assert "Lesson create failed" in courses
    assert "db.rollback()" in courses
