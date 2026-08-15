from datetime import datetime
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    Lesson, LessonProgress, LessonVideoProfile, LessonCheckpoint, CheckpointAttempt,
    LessonFlashcard, Homework, MediaAsset,
)
from .api_v1_common import user
from .access import authorized_for_course, content_schedule_allows, lesson_access_state
from .cloudflare_stream import extract_stream_uid, stream_embed_path, stream_edge_ready
from .security import sign_lesson, sha256

router = APIRouter(tags=["api-v1-lesson"])


def _student_lesson(lesson_id: int, request: Request, db: Session):
    resolved = user(request, db)
    if resolved.role != "student":
        raise HTTPException(403, "Student account required")
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not content_schedule_allows(db, "lesson", lesson_id):
        raise HTTPException(404)
    if not authorized_for_course(db, resolved, lesson.course_id):
        raise HTTPException(403)
    access = lesson_access_state(db, resolved, lesson)
    if not access["unlocked"]:
        raise HTTPException(403, access["reason"])
    return resolved, lesson


def _session_record(request: Request):
    rec = getattr(request.state, "_lms_session_record", None)
    if rec is None:
        raise HTTPException(401, "Authentication required")
    return rec


def _direct_proxy_enabled() -> bool:
    return os.getenv("DIRECT_VIDEO_PROXY_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


@router.get('/lessons/{lesson_id}/experience')
def lesson_experience(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    resolved, lesson = _student_lesson(lesson_id, request, db)
    rec = _session_record(request)
    progress = db.query(LessonProgress).filter_by(user_id=resolved.id, lesson_id=lesson.id).first()
    profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson.id).first()

    trace_code = sha256(f"{resolved.id}:{lesson.id}:{rec.token_hash}")[:10].upper()
    watermark = f"{resolved.name} • ID {resolved.id} • SESSION {trace_code}"

    playback = {"kind": "none", "url": None, "edge_ready": False}
    if lesson.video_url:
        if profile and profile.provider == "cloudflare":
            path = stream_embed_path(lesson.video_url, lesson.id, resolved.id)
            playback = {
                "kind": "cloudflare" if path else "unavailable",
                "url": path,
                "edge_ready": bool(path and stream_edge_ready()),
            }
        else:
            lower = lesson.video_url.lower().split("?", 1)[0]
            if (lower.endswith(".mp4") or lower.endswith(".webm")) and _direct_proxy_enabled():
                token = sign_lesson(lesson.id, resolved.id, rec.token_hash, ttl=300)
                playback = {
                    "kind": "direct_proxy",
                    "url": f"/protected/video/{lesson.id}?token={token}",
                    "edge_ready": True,
                }
            elif extract_stream_uid(lesson.video_url):
                path = stream_embed_path(lesson.video_url, lesson.id, resolved.id)
                playback = {
                    "kind": "cloudflare" if path else "unavailable",
                    "url": path,
                    "edge_ready": bool(path and stream_edge_ready()),
                }
            else:
                # Never expose a permanent third-party/raw video URL to the separated frontend.
                playback = {"kind": "backend_only", "url": f"/lesson/{lesson.id}", "edge_ready": False}

    checkpoints = db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id, published=True).order_by(
        LessonCheckpoint.timestamp_seconds, LessonCheckpoint.id
    ).all()
    attempts = {
        row.checkpoint_id: row for row in db.query(CheckpointAttempt).filter(
            CheckpointAttempt.student_id == resolved.id,
            CheckpointAttempt.checkpoint_id.in_([c.id for c in checkpoints] or [-1]),
        ).all()
    }
    checkpoint_data = []
    for cp in checkpoints:
        attempt = attempts.get(cp.id)
        checkpoint_data.append({
            "id": cp.id,
            "timestamp_seconds": cp.timestamp_seconds,
            "question": cp.question,
            "options": {"A": cp.option_a, "B": cp.option_b, "C": cp.option_c, "D": cp.option_d},
            "answered": bool(attempt),
            "selected": attempt.answer if attempt else None,
            "is_correct": bool(attempt and attempt.is_correct),
            "explanation": cp.explanation if attempt else None,
            "correct": cp.correct if attempt else None,
        })

    flashcards = db.query(LessonFlashcard).filter_by(lesson_id=lesson.id, published=True).order_by(
        LessonFlashcard.order_index, LessonFlashcard.id
    ).all()
    homeworks = db.query(Homework).filter(Homework.lesson_id == lesson.id, Homework.published == True).order_by(Homework.id).all()
    assets = db.query(MediaAsset).filter_by(lesson_id=lesson.id).order_by(MediaAsset.id).all()

    return {"data": {
        "id": lesson.id,
        "course_id": lesson.course_id,
        "title": lesson.title,
        "body": lesson.body or "",
        "completed": bool(progress and progress.completed),
        "watched_seconds": int(progress.watched_seconds or 0) if progress else 0,
        "watermark": watermark,
        "playback": playback,
        "video_profile": ({
            "provider": profile.provider,
            "processing_status": profile.processing_status,
            "drm_mode": profile.drm_mode,
            "duration_seconds": profile.duration_seconds,
            "stream_type": profile.stream_type,
        } if profile else None),
        "checkpoints": checkpoint_data,
        "flashcards": [{"id": c.id, "front": c.front, "back": c.back} for c in flashcards],
        "homeworks": [{"id": h.id, "title": h.title, "instructions": h.instructions or "", "launch_url": f"/homework/{h.id}"} for h in homeworks],
        "assets": [{"id": a.id, "name": a.original_name, "mime_type": a.mime_type, "launch_url": f"/protected/media/{a.id}"} for a in assets],
        "backend_fallback_url": f"/lesson/{lesson.id}",
    }}
