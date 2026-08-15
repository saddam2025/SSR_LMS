from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Enrollment, HomeworkSubmission, LessonProgress, ParentStudent, QuizAttempt, User
from ..request_context import audit, require_role, template_context as ctx
from ..security import check_csrf
from ..services.student_activity import student_weekly_attendance
from ..services.template_rendering import render_template

router = APIRouter()

@router.get("/parent", response_class=HTMLResponse)
def parent_dashboard(request: Request, db: Session = Depends(get_db)):
    parent = require_role(request, db, "parent")
    links = db.query(ParentStudent).filter_by(parent_id=parent.id).all()
    children = []
    for link in links:
        student = db.get(User, link.student_id)
        if not student: continue
        enrollments = db.query(Enrollment).filter_by(user_id=student.id, active=True).all()
        attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == student.id, QuizAttempt.status == "submitted").order_by(QuizAttempt.id.desc()).limit(12).all()
        submitted = db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id == student.id).order_by(HomeworkSubmission.id.desc()).limit(12).all()
        completed = db.query(LessonProgress).filter_by(user_id=student.id, completed=True).count()
        watched = db.query(func.coalesce(func.sum(LessonProgress.watched_seconds), 0)).filter(LessonProgress.user_id == student.id).scalar() or 0
        avg = round(sum(a.score / a.total * 100 for a in attempts if a.total) / max(1, len([a for a in attempts if a.total]))) if attempts else 0
        attendance = student_weekly_attendance(db, student.id, 7)
        children.append({"student": student, "enrollments": enrollments, "attempts": attempts, "homeworks": submitted, "completed": completed, "watched": int(watched), "avg": avg, "attendance": attendance})
    return render_template("parent_dashboard.html", ctx(request, db, children=children))

@router.post("/admin/parents/link")
def admin_link_parent(request: Request, parent_id: int = Form(...), student_id: int = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    parent, student = db.get(User, parent_id), db.get(User, student_id)
    if not parent or parent.role != "parent" or not student or student.role != "student": raise HTTPException(400, "الحسابات المختارة غير صالحة")
    if not db.query(ParentStudent).filter_by(parent_id=parent.id, student_id=student.id).first():
        db.add(ParentStudent(parent_id=parent.id, student_id=student.id)); db.commit(); audit(db, request, admin, "parent_student_linked", {"parent_id": parent.id, "student_id": student.id})
    return RedirectResponse("/admin/users", 303)

@router.get('/parent/report/{student_id}', response_class=HTMLResponse)
def parent_weekly_report(student_id:int,request:Request,db:Session=Depends(get_db)):
    from datetime import datetime, timedelta
    parent=require_role(request,db,'parent')
    if not db.query(ParentStudent).filter_by(parent_id=parent.id,student_id=student_id).first(): raise HTTPException(403)
    student=db.get(User,student_id); since=datetime.utcnow()-timedelta(days=7)
    progress=db.query(LessonProgress).filter(LessonProgress.user_id==student_id,LessonProgress.updated_at>=since).all()
    attempts=db.query(QuizAttempt).filter(QuizAttempt.user_id==student_id,QuizAttempt.created_at>=since,QuizAttempt.status=='submitted').all()
    submissions=db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id==student_id,HomeworkSubmission.submitted_at>=since).all()
    watched=sum(x.watched_seconds for x in progress); completed=sum(1 for x in progress if x.completed)
    avg=round(sum((a.score/a.total*100) for a in attempts if a.total)/max(1,len([a for a in attempts if a.total]))) if attempts else 0
    alerts=[]
    if completed==0: alerts.append('لم يُكمل الطالب أي درس خلال آخر 7 أيام.')
    if attempts and avg<60: alerts.append('متوسط الاختبارات أقل من 60% ويحتاج مراجعة.')
    attendance=student_weekly_attendance(db,student_id,7)
    if attendance['inactive_days']>=3: alerts.append(f"لا يوجد نشاط للطالب منذ {attendance['inactive_days']} أيام.")
    if attendance['present']<2: alerts.append('معدل النشاط الأسبوعي منخفض ويحتاج متابعة.')
    return render_template('parent_weekly_report.html',ctx(request,db,student=student,watched=watched,completed=completed,attempts=attempts,submissions=submissions,avg=avg,alerts=alerts,since=since,attendance=attendance))
