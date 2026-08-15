from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .db import get_db
from .models import Course, Lesson, Enrollment, LessonProgress, QuizAttempt, Notification
from .cache import get_json, set_json
from .api_v1_common import user
from .access import authorized_for_course, content_schedule_allows, lesson_access_state

router = APIRouter(tags=["api-v1-student"])


def _student(request: Request, db: Session):
    resolved = user(request, db)
    if resolved.role != 'student':
        raise HTTPException(403, 'Student account required')
    return resolved

@router.get('/courses')
def courses(request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    uid = resolved.id
    key = f'api:v1:courses:{uid}'
    cached = get_json(key)
    if cached is not None:
        return {'data': cached, 'cached': True}
    enrollments = db.query(Enrollment).filter_by(user_id=uid, active=True).all()
    now = datetime.utcnow()
    ids = [e.course_id for e in enrollments if not e.expires_at or e.expires_at > now]
    rows = db.query(Course).filter(Course.id.in_(ids), Course.published == True).all() if ids else []
    data = [{'id': c.id, 'title': c.title, 'grade': c.grade, 'price': c.price} for c in rows]
    set_json(key, data, 45)
    return {'data': data, 'cached': False}

@router.get('/courses/{course_id}')
def course_details(course_id: int, request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    course = db.get(Course, course_id)
    if not course or not course.published:
        raise HTTPException(404)
    if not authorized_for_course(db, resolved, course.id):
        raise HTTPException(403)
    return {'data': {'id': course.id, 'title': course.title, 'grade': course.grade, 'price': course.price}}

@router.get('/courses/{course_id}/lessons')
def lessons(course_id: int, request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    course = db.get(Course, course_id)
    if not course or not course.published:
        raise HTTPException(404)
    if not authorized_for_course(db, resolved, course_id):
        raise HTTPException(403)
    rows = db.query(Lesson).filter_by(course_id=course_id, published=True).order_by(Lesson.order_index, Lesson.id).all()
    rows = [lesson for lesson in rows if content_schedule_allows(db, 'lesson', lesson.id)]
    progress = {p.lesson_id: p for p in db.query(LessonProgress).filter(
        LessonProgress.user_id == resolved.id,
        LessonProgress.lesson_id.in_([x.id for x in rows] or [-1]),
    ).all()}
    data = []
    for lesson in rows:
        access = lesson_access_state(db, resolved, lesson)
        data.append({
            'id': lesson.id,
            'title': lesson.title,
            'order': lesson.order_index,
            'completed': bool(progress.get(lesson.id) and progress[lesson.id].completed),
            'unlocked': bool(access['unlocked']),
            'lock_reason': '' if access['unlocked'] else access['reason'],
            'launch_url': f'/lesson/{lesson.id}' if access['unlocked'] else None,
            'frontend_launch_url': f'/student/lesson.html?id={lesson.id}' if access['unlocked'] else None,
        })
    return {'data': data}

@router.get('/lessons/{lesson_id}')
def lesson_details(lesson_id: int, request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    lesson = db.get(Lesson, lesson_id)
    if not lesson or not lesson.published or not content_schedule_allows(db, 'lesson', lesson.id):
        raise HTTPException(404)
    if not authorized_for_course(db, resolved, lesson.course_id):
        raise HTTPException(403)
    access = lesson_access_state(db, resolved, lesson)
    if not access['unlocked']:
        raise HTTPException(403, access['reason'])
    progress = db.query(LessonProgress).filter_by(user_id=resolved.id, lesson_id=lesson.id).first()
    return {'data': {
        'id': lesson.id,
        'course_id': lesson.course_id,
        'title': lesson.title,
        'body': lesson.body or '',
        'completed': bool(progress and progress.completed),
        # Playback remains a backend-owned protected surface in V60.
        'launch_url': f'/lesson/{lesson.id}',
    }}

@router.get('/me/summary')
def summary(request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    uid = resolved.id
    return {'data': {
        'active_courses': db.query(Enrollment).filter(Enrollment.user_id == uid, Enrollment.active == True).filter((Enrollment.expires_at.is_(None)) | (Enrollment.expires_at > datetime.utcnow())).count(),
        'completed_lessons': db.query(LessonProgress).filter_by(user_id=uid, completed=True).count(),
        'quiz_attempts': db.query(QuizAttempt).filter_by(user_id=uid).count(),
        'unread_notifications': db.query(Notification).filter(Notification.user_id == uid, Notification.read_at.is_(None)).count(),
    }}

@router.get('/notifications')
def notifications(request: Request, db: Session = Depends(get_db)):
    resolved = _student(request, db)
    rows = db.query(Notification).filter_by(user_id=resolved.id).order_by(Notification.id.desc()).limit(30).all()
    return {'data': [{
        'id': row.id,
        'title': row.title,
        'body': row.body,
        'kind': row.kind,
        'read': row.read_at is not None,
    } for row in rows]}
