from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User, StudyAssistantLog, StudentRemediationItem, StudentRemediationPlan
from ..request_context import audit, require_role, template_context as ctx
from ..security import check_csrf
from ..services.remediation import remediation_context, smart_tutor_recommendations
from ..services.template_rendering import render_template

router = APIRouter()

@router.get("/smart-tutor", response_class=HTMLResponse)
def smart_tutor_page(request: Request, db: Session = Depends(get_db)):
    u=require_role(request, db, "student")
    intel, recommendations=smart_tutor_recommendations(db, u.id)
    recent=db.query(StudyAssistantLog).filter_by(user_id=u.id).order_by(StudyAssistantLog.id.desc()).limit(8).all()
    return render_template("student_smart_tutor.html", ctx(request, db, intel=intel, recommendations=recommendations, recent=recent))

@router.get("/learning-plan", response_class=HTMLResponse)
def student_learning_plan(request: Request, db: Session = Depends(get_db)):
    u=require_role(request, db, "student")
    intel, plan, items, progress=remediation_context(db, u.id)
    return render_template("student_learning_plan.html", ctx(request, db, intel=intel, plan=plan, items=items, plan_progress=progress))

@router.post("/learning-plan/regenerate")
def regenerate_learning_plan(request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u=require_role(request, db, "student")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    remediation_context(db, u.id, force=True)
    audit(db, request, u, "learning_plan_regenerated")
    return RedirectResponse("/learning-plan", 303)

@router.post("/learning-plan/item/{item_id}/toggle")
def toggle_learning_plan_item(item_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u=require_role(request, db, "student")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    item=db.get(StudentRemediationItem, item_id); plan=db.get(StudentRemediationPlan, item.plan_id) if item else None
    if not item or not plan or plan.user_id != u.id or not plan.active: raise HTTPException(404)
    item.completed=not item.completed; item.completed_at=datetime.utcnow() if item.completed else None; db.commit()
    return RedirectResponse("/learning-plan", 303)

@router.get("/admin/students/{student_id}/learning-plan", response_class=HTMLResponse)
def admin_student_learning_plan(student_id: int, request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "support", "content_manager")
    student=db.get(User, student_id)
    if not student or student.role != "student": raise HTTPException(404)
    intel, plan, items, progress=remediation_context(db, student.id)
    return render_template("admin_student_learning_plan.html", ctx(request, db, student=student, intel=intel, plan=plan, items=items, plan_progress=progress))
