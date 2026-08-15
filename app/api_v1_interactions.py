import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    AuditLog, CheckpointAttempt, DiscussionPost, Homework, Lesson, LessonCheckpoint,
    LessonFlashcard, PointLedger, StudyAssistantLog, User,
)
from .api_v1_common import user
from .access import authorized_for_course, content_schedule_allows, lesson_access_state
from .security import check_csrf

router = APIRouter(tags=["api-v1-lesson-interactions"])


class CheckpointAnswer(BaseModel):
    answer: str


class AssistantQuestion(BaseModel):
    question: str
    mode: str = "explain"


class DiscussionCreate(BaseModel):
    body: str
    parent_id: int | None = None


def _client_ip(request: Request) -> str:
    forwarded = (request.headers.get("cf-connecting-ip") or request.headers.get("x-forwarded-for") or "").split(",", 1)[0].strip()
    return (forwarded or (request.client.host if request.client else ""))[:80]


def _audit(db: Session, request: Request, resolved: User, action: str, metadata: dict | None = None) -> None:
    db.add(AuditLog(user_id=resolved.id, action=action, ip=_client_ip(request), metadata_json=json.dumps(metadata or {}, ensure_ascii=False)))


def _csrf(request: Request) -> None:
    token = request.headers.get("x-csrf-token", "")
    if not check_csrf(request.session, token):
        raise HTTPException(403, "CSRF failed")


def _student_lesson(lesson_id: int, request: Request, db: Session):
    resolved = user(request, db)
    if resolved.role != "student":
        raise HTTPException(403, "Student account required")
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not content_schedule_allows(db, "lesson", lesson.id):
        raise HTTPException(404)
    if not authorized_for_course(db, resolved, lesson.course_id):
        raise HTTPException(403)
    access = lesson_access_state(db, resolved, lesson)
    if not access["unlocked"]:
        raise HTTPException(403, access["reason"])
    return resolved, lesson


def _tokens(value: str) -> set[str]:
    stop = {"من","في","على","الى","إلى","عن","هو","هي","ما","ماذا","كيف","ليه","لماذا","the","a","an","is","are","of","to","in","on","and","or","what","how"}
    return {x for x in re.findall(r"[\w\u0600-\u06FF]+", (value or "").lower()) if len(x) >= 2 and x not in stop}


def _grounded_answer(db: Session, lesson: Lesson, question: str, mode: str) -> tuple[str, str]:
    tokens = _tokens(question)
    sources: list[tuple[str, str]] = []
    for part in re.split(r"[\n\r.!?؟]+", lesson.body or ""):
        part = part.strip()
        if len(part) >= 12:
            sources.append(("شرح الدرس", part[:900]))
    for h in db.query(Homework).filter(Homework.lesson_id == lesson.id, Homework.published == True).all():
        if (h.instructions or "").strip():
            sources.append((f"الواجب: {h.title}", h.instructions.strip()[:900]))
    checkpoints = db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id, published=True).all()
    for cp in checkpoints:
        if (cp.explanation or "").strip():
            sources.append(("تفسير سؤال تفاعلي", cp.explanation.strip()[:900]))
    for card in db.query(LessonFlashcard).filter_by(lesson_id=lesson.id, published=True).all():
        sources.append((f"Flashcard: {card.front}", (card.back or "").strip()[:900]))
    ranked = []
    for kind, text_value in sources:
        score = len(tokens & _tokens(text_value))
        if "واجب" in question and kind.startswith("الواجب"):
            score += 3
        ranked.append((score, kind, text_value))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    chosen = [x for x in ranked if x[0] > 0][:3] or ranked[:3]
    if not chosen:
        return "لا يوجد محتوى نصي كافٍ في هذا الدرس للإجابة بدقة.", "no_context"
    labels = {"explain":"شرح مبسط", "review":"مراجعة مركزة", "practice":"تدريب موجه", "homework":"استعداد للواجب"}
    clean_mode = mode if mode in labels else "explain"
    lines = [labels[clean_mode], "• الإجابة مبنية فقط على المحتوى التعليمي الموجود داخل هذا الدرس."]
    if clean_mode == "practice":
        lines.append("• حاول الإجابة بنفسك أولًا ثم استخدم النقاط التالية للمراجعة.")
    for _, kind, text_value in chosen:
        lines.append(f"• {kind}: {text_value}")
    return "\n".join(lines), f"lesson_context_{clean_mode}"


@router.post('/lessons/{lesson_id}/checkpoints/{checkpoint_id}/answer')
def checkpoint_answer(lesson_id: int, checkpoint_id: int, payload: CheckpointAnswer, request: Request, db: Session = Depends(get_db)):
    resolved, lesson = _student_lesson(lesson_id, request, db)
    _csrf(request)
    cp = db.get(LessonCheckpoint, checkpoint_id)
    if not cp or cp.lesson_id != lesson.id or not cp.published:
        raise HTTPException(404)
    selected = (payload.answer or "").strip().upper()[:1]
    if selected not in {"A", "B", "C", "D"}:
        raise HTTPException(400, "Invalid answer")
    rec = db.query(CheckpointAttempt).filter_by(checkpoint_id=cp.id, student_id=resolved.id).first()
    first = rec is None
    if not rec:
        rec = CheckpointAttempt(checkpoint_id=cp.id, student_id=resolved.id)
        db.add(rec)
    rec.answer = selected
    rec.is_correct = selected == (cp.correct or "").upper()
    rec.attempted_at = datetime.utcnow()
    if first:
        exists = db.query(PointLedger).filter_by(user_id=resolved.id, reason="سؤال تفاعلي داخل الدرس", ref_type="checkpoint", ref_id=cp.id).first()
        if not exists:
            db.add(PointLedger(user_id=resolved.id, points=5 if rec.is_correct else 2, reason="سؤال تفاعلي داخل الدرس", ref_type="checkpoint", ref_id=cp.id))
    _audit(db, request, resolved, "lesson_checkpoint_answered_api", {"lesson_id": lesson.id, "checkpoint_id": cp.id, "correct": rec.is_correct})
    db.commit()
    return {"data": {"checkpoint_id": cp.id, "selected": rec.answer, "is_correct": bool(rec.is_correct), "correct": cp.correct, "explanation": cp.explanation or ""}}


@router.post('/lessons/{lesson_id}/assistant')
def assistant(lesson_id: int, payload: AssistantQuestion, request: Request, db: Session = Depends(get_db)):
    resolved, lesson = _student_lesson(lesson_id, request, db)
    _csrf(request)
    question = (payload.question or "").strip()[:1000]
    if len(question) < 2:
        raise HTTPException(400, "اكتب سؤالًا واضحًا")
    mode = (payload.mode or "explain").strip().lower()
    answer, source_kind = _grounded_answer(db, lesson, question, mode)
    db.add(StudyAssistantLog(lesson_id=lesson.id, user_id=resolved.id, question=question, answer=answer, source_kind=source_kind))
    _audit(db, request, resolved, "study_assistant_question_api", {"lesson_id": lesson.id, "source_kind": source_kind})
    db.commit()
    return {"data": {"question": question, "answer": answer, "source_kind": source_kind, "grounded_only": True}}


@router.get('/lessons/{lesson_id}/discussion')
def discussion_list(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    _, lesson = _student_lesson(lesson_id, request, db)
    posts = db.query(DiscussionPost).filter_by(lesson_id=lesson.id, status="visible").order_by(DiscussionPost.id).limit(100).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_([p.user_id for p in posts] or [-1])).all()}
    return {"data": [{"id": p.id, "parent_id": p.parent_id, "body": p.body, "author": users[p.user_id].name if p.user_id in users else "طالب", "created_at": p.created_at.isoformat() if p.created_at else None} for p in posts]}


@router.post('/lessons/{lesson_id}/discussion')
def discussion_create(lesson_id: int, payload: DiscussionCreate, request: Request, db: Session = Depends(get_db)):
    resolved, lesson = _student_lesson(lesson_id, request, db)
    _csrf(request)
    text = (payload.body or "").strip()
    if len(text) < 2 or len(text) > 2000:
        raise HTTPException(400, "طول المشاركة غير صالح")
    parent = None
    if payload.parent_id is not None:
        parent = db.get(DiscussionPost, payload.parent_id)
        if not parent or parent.lesson_id != lesson.id or parent.status != "visible":
            raise HTTPException(400, "Invalid parent")
    post = DiscussionPost(lesson_id=lesson.id, user_id=resolved.id, parent_id=parent.id if parent else None, body=text, status="visible")
    db.add(post)
    _audit(db, request, resolved, "discussion_posted_api", {"lesson_id": lesson.id})
    db.commit(); db.refresh(post)
    return {"data": {"id": post.id, "parent_id": post.parent_id, "body": post.body, "author": resolved.name, "created_at": post.created_at.isoformat() if post.created_at else None}}
