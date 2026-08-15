from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Course, Lesson, Quiz, PointLedger, StudentProfile
from ..request_context import require_user, require_role, template_context as ctx, audit
from ..security import check_csrf
from ..services.auth import normalize_phone
from ..access import authorized_for_course
from ..services.dashboard_experience import points_total, level_for, student_plan
from ..services.template_rendering import render_template
router=APIRouter()

@router.get("/search", response_class=HTMLResponse)
def search_page(request: Request, q: str = "", db: Session = Depends(get_db)):
    u=require_user(request, db); term=(q or "").strip()[:100]
    courses=[]; lessons=[]; quizzes=[]
    if term:
        like=f"%{term}%"
        cq=db.query(Course).filter(or_(Course.title.ilike(like), Course.description.ilike(like)))
        courses=[c for c in cq.limit(30).all() if c.published and authorized_for_course(db,u,c.id)]
        lq=db.query(Lesson).filter(or_(Lesson.title.ilike(like), Lesson.body.ilike(like)), Lesson.published==True).limit(50).all()
        lessons=[l for l in lq if authorized_for_course(db,u,l.course_id)]
        qq=db.query(Quiz).filter(Quiz.title.ilike(like), Quiz.published==True).limit(30).all()
        quizzes=[z for z in qq if authorized_for_course(db,u,z.course_id)]
    return render_template("search.html", ctx(request,db,q=term,courses=courses,lessons=lessons,quizzes=quizzes))

@router.get("/study-plan", response_class=HTMLResponse)
def study_plan_page(request: Request, db: Session=Depends(get_db)):
    u=require_role(request,db,"student")
    return render_template("study_plan.html",ctx(request,db,tasks=student_plan(db,u.id),points=points_total(db,u.id),level=level_for(points_total(db,u.id))[0]))

@router.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(request: Request, db: Session=Depends(get_db)):
    require_user(request,db)
    rows=(db.query(User.id,User.name,func.coalesce(func.sum(PointLedger.points),0).label("pts"))
          .outerjoin(PointLedger,PointLedger.user_id==User.id).filter(User.role=="student",User.is_active==True)
          .group_by(User.id,User.name).order_by(func.coalesce(func.sum(PointLedger.points),0).desc()).limit(50).all())
    return render_template("leaderboard.html",ctx(request,db,rows=rows))

@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session=Depends(get_db)):
    u=require_role(request,db,"student")
    profile=db.query(StudentProfile).filter_by(user_id=u.id).first() or StudentProfile(user_id=u.id)
    return render_template("student_profile.html",ctx(request,db,profile=profile))

@router.post("/profile")
def profile_update(request:Request, phone:str=Form(""),father_phone:str=Form(""),mother_phone:str=Form(""),school:str=Form(""),governorate:str=Form(""),grade:str=Form(""),section:str=Form(""),parent_job:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"student")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    p=db.query(StudentProfile).filter_by(user_id=u.id).first()
    if not p: p=StudentProfile(user_id=u.id); db.add(p)
    normalized=normalize_phone(phone)
    if normalized:
        other=db.query(StudentProfile).filter(StudentProfile.phone==normalized,StudentProfile.user_id!=u.id).first()
        if other: raise HTTPException(409,"رقم الهاتف مستخدم بحساب آخر")
    p.phone=normalized; p.father_phone=normalize_phone(father_phone); p.mother_phone=normalize_phone(mother_phone)
    p.school=school.strip()[:180]; p.governorate=governorate.strip()[:100]; p.grade=grade.strip()[:80]; p.section=section.strip()[:80]; p.parent_job=parent_job.strip()[:120]
    db.commit(); audit(db,request,u,"student_profile_updated")
    return RedirectResponse("/profile",303)

