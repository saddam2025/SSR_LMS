from sqlalchemy import func
from sqlalchemy.orm import Session
from ..models import Course, Enrollment, Homework, HomeworkSubmission, Lesson, LessonProgress, PointLedger

def points_total(db: Session, user_id: int) -> int:
    return int(db.query(func.coalesce(func.sum(PointLedger.points), 0)).filter(PointLedger.user_id == user_id).scalar() or 0)

def level_for(points: int):
    if points >= 1500: return ("أسطورة المستشار", 6)
    if points >= 800: return ("متفوق", 5)
    if points >= 400: return ("متقدم", 4)
    if points >= 200: return ("مجتهد", 3)
    if points >= 80: return ("متعلم نشط", 2)
    return ("بداية قوية", 1)

def student_plan(db: Session, user_id: int, enrollments=None, courses=None):
    if enrollments is None: enrollments=db.query(Enrollment).filter_by(user_id=user_id,active=True).all()
    course_ids=[e.course_id for e in enrollments]
    if not course_ids: return []
    if courses is None: courses={c.id:c for c in db.query(Course).filter(Course.id.in_(course_ids)).all()}
    lessons=db.query(Lesson).filter(Lesson.course_id.in_(course_ids),Lesson.published==True).order_by(Lesson.course_id,Lesson.order_index,Lesson.id).all()
    lesson_ids=[l.id for l in lessons]
    completed={p.lesson_id for p in db.query(LessonProgress).filter(LessonProgress.user_id==user_id,LessonProgress.lesson_id.in_(lesson_ids),LessonProgress.completed==True).all()} if lesson_ids else set()
    by_course={}
    for l in lessons: by_course.setdefault(l.course_id,[]).append(l)
    homeworks=db.query(Homework).filter(Homework.course_id.in_(course_ids),Homework.published==True).order_by(Homework.course_id,Homework.id).all()
    hw_ids=[h.id for h in homeworks]
    submitted={r.homework_id for r in db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id==user_id,HomeworkSubmission.homework_id.in_(hw_ids)).all()} if hw_ids else set()
    hw_by_course={}
    for h in homeworks: hw_by_course.setdefault(h.course_id,[]).append(h)
    tasks=[]
    for e in enrollments:
        c=courses.get(e.course_id)
        if not c: continue
        l=next((x for x in by_course.get(c.id,[]) if x.id not in completed),None)
        if l: tasks.append({"kind":"lesson","title":l.title,"course":c.title,"url":f"/lesson/{l.id}"})
        h=next((x for x in hw_by_course.get(c.id,[]) if x.id not in submitted),None)
        if h: tasks.append({"kind":"homework","title":h.title,"course":c.title,"url":f"/homework/{h.id}"})
    return tasks[:6]
