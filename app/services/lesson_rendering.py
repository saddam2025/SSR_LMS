import os
from sqlalchemy.orm import Session
from fastapi import Request
from ..cloudflare_stream import stream_edge_ready, stream_embed_path
from ..models import (
    User, Lesson, MediaAsset, DiscussionPost, LessonCheckpoint, CheckpointAttempt,
    LessonFlashcard, Homework, OfflineLessonPolicy, LessonVideoProfile,
)
from ..request_context import session_record, template_context
from ..security import sign_lesson, sha256
from .learning_runtime import direct_video_proxy_enabled
from .template_rendering import render_template

def video_token_ttl() -> int:
    try: value = int(os.getenv("VIDEO_TOKEN_TTL_SECONDS", "7200"))
    except ValueError: value = 7200
    return max(900, min(value, 14400))

def render_lesson_page(request: Request, db: Session, lesson: Lesson, u: User, *, assistant_question: str = "", assistant_answer: str = "", is_production: bool | None = None):
    rec = session_record(request, db)
    token = sign_lesson(lesson.id, u.id, rec.token_hash)
    video_token = sign_lesson(lesson.id, u.id, rec.token_hash, ttl=video_token_ttl())
    trace_code = sha256(f"{u.id}:{lesson.id}:{rec.token_hash}")[:10].upper()
    watermark = f"{u.name} • ID {u.id} • SESSION {trace_code}"
    assets = db.query(MediaAsset).filter_by(lesson_id=lesson.id).order_by(MediaAsset.id).all()
    posts = db.query(DiscussionPost).filter_by(lesson_id=lesson.id, status="visible").order_by(DiscussionPost.id).limit(100).all()
    post_users = {x.id: x for x in db.query(User).filter(User.id.in_([p.user_id for p in posts] or [-1])).all()}
    checkpoints = db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id, published=True).order_by(LessonCheckpoint.timestamp_seconds, LessonCheckpoint.id).all()
    attempt_map = {a.checkpoint_id: a for a in db.query(CheckpointAttempt).filter(CheckpointAttempt.student_id == u.id, CheckpointAttempt.checkpoint_id.in_([c.id for c in checkpoints] or [-1])).all()} if u.role == "student" else {}
    flashcards = db.query(LessonFlashcard).filter_by(lesson_id=lesson.id, published=True).order_by(LessonFlashcard.order_index, LessonFlashcard.id).all()
    related_homework = db.query(Homework).filter(Homework.lesson_id == lesson.id, Homework.published == True).order_by(Homework.id).all()
    offline_policy = db.query(OfflineLessonPolicy).filter_by(lesson_id=lesson.id).first()
    offline_provider_ready = bool((os.getenv("OFFLINE_DRM_LICENSE_URL") or os.getenv("DRM_LICENSE_SERVER_URL") or "").strip())
    video_profile = db.query(LessonVideoProfile).filter_by(lesson_id=lesson.id).first()
    stream_player_path = None
    if video_profile and video_profile.provider == "cloudflare":
        stream_player_path = stream_embed_path(lesson.video_url, lesson.id, u.id)
    if is_production is None:
        is_production = os.getenv("ENV") == "production"
    return render_template("lesson.html", template_context(
        request, db, lesson=lesson, media_token=token, video_token=video_token,
        watermark=watermark, watermark_name=u.name, assets=assets,
        discussion_posts=posts, discussion_users=post_users, checkpoints=checkpoints,
        checkpoint_attempts=attempt_map, flashcards=flashcards, related_homework=related_homework,
        assistant_question=assistant_question, assistant_answer=assistant_answer,
        offline_policy=offline_policy, offline_provider_ready=offline_provider_ready, video_profile=video_profile,
        direct_video_proxy_enabled=direct_video_proxy_enabled(is_production=is_production),
        stream_player_path=stream_player_path, stream_edge_ready=stream_edge_ready(),
    ))
