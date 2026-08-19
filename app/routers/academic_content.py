from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from ..db import engine, get_db
from ..models import (
    User, Course, Lesson, Quiz, Question, Homework, HomeworkSubmission, Enrollment, MediaAsset,
    ContentUnit, LessonUnitAssignment, QuizUnitAssignment, HomeworkUnitAssignment, CourseAcademicPeriod, ContentSchedule,
    LessonVideoProfile, LessonDripRule, QuizQuestionSetting, RevisionPlan, RevisionTask, RevisionTaskProgress, StudentProfile
)
from ..request_context import audit, require_role, require_user, template_context as ctx
from ..security import check_csrf
from ..services.template_rendering import render_template
from ..services.academic_content import schedule_status, target_schedule, revision_target, revision_target_url

router = APIRouter()
GRADE_ORDER = ["الصف الأول الثانوي", "الصف الثاني الثانوي عام", "الصف الثاني بكالوريا", "الصف الثالث الثانوي"]

def _pg_xact_lock(db, namespace: int, entity_id: int):
    if engine.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :entity)"), {"ns": int(namespace), "entity": int(entity_id) & 0x7FFFFFFF})

def _content_center_payload(db: Session):
    courses = db.query(Course).order_by(Course.grade, Course.id).all()
    course_map = {c.id: c for c in courses}
    periods = {x.course_id: x for x in db.query(CourseAcademicPeriod).all()}
    units = db.query(ContentUnit).order_by(ContentUnit.course_id, ContentUnit.order_index, ContentUnit.id).all()
    units_by_course = {}
    for unit in units:
        units_by_course.setdefault(unit.course_id, []).append(unit)
    lesson_assign = {x.lesson_id: x.unit_id for x in db.query(LessonUnitAssignment).all()}
    quiz_assign = {x.quiz_id: x.unit_id for x in db.query(QuizUnitAssignment).all()}
    hw_assign = {x.homework_id: x.unit_id for x in db.query(HomeworkUnitAssignment).all()}
    lessons = db.query(Lesson).order_by(Lesson.course_id, Lesson.order_index, Lesson.id).all()
    quizzes = db.query(Quiz).order_by(Quiz.course_id, Quiz.id).all()
    homeworks = db.query(Homework).order_by(Homework.course_id, Homework.id).all()
    assets = db.query(MediaAsset).all()
    assets_by_lesson = {}
    for a in assets:
        if a.lesson_id:
            assets_by_lesson[a.lesson_id] = assets_by_lesson.get(a.lesson_id, 0) + 1
    rows = {}
    for course in courses:
        rows[course.id] = {"course": course, "period": periods.get(course.id), "lessons": [], "quizzes": [], "homeworks": [], "units": units_by_course.get(course.id, [])}
    for lesson in lessons:
        if lesson.course_id in rows:
            rows[lesson.course_id]["lessons"].append((lesson, lesson_assign.get(lesson.id), assets_by_lesson.get(lesson.id, 0)))
    for quiz in quizzes:
        if quiz.course_id in rows:
            rows[quiz.course_id]["quizzes"].append((quiz, quiz_assign.get(quiz.id)))
    for hw in homeworks:
        if hw.course_id in rows:
            rows[hw.course_id]["homeworks"].append((hw, hw_assign.get(hw.id)))
    grade_groups = []
    grades = GRADE_ORDER + sorted({c.grade for c in courses if c.grade not in GRADE_ORDER})
    for grade in grades:
        grade_courses = [rows[c.id] for c in courses if c.grade == grade]
        if grade_courses or grade in GRADE_ORDER:
            grade_groups.append((grade, grade_courses))
    schedules = db.query(ContentSchedule).all()
    now_schedule = datetime.utcnow()
    schedule_map = {f"{x.content_type}:{x.content_id}": x for x in schedules}
    schedule_stats = {
        "scheduled": sum(1 for x in schedules if schedule_status(x, now_schedule) == "scheduled"),
        "live": sum(1 for x in schedules if schedule_status(x, now_schedule) == "live"),
        "expired": sum(1 for x in schedules if schedule_status(x, now_schedule) == "expired"),
    }
    stats = {
        "courses": len(courses),
        "units": len(units),
        "lessons": len(lessons),
        "draft_lessons": sum(1 for x in lessons if not x.published),
        "quizzes": len(quizzes),
        "homeworks": len(homeworks),
        "assets": len(assets),
        "unassigned": sum(1 for x in lessons if x.id not in lesson_assign) + sum(1 for x in quizzes if x.id not in quiz_assign) + sum(1 for x in homeworks if x.id not in hw_assign),
    }
    return grade_groups, course_map, stats, schedule_map, schedule_stats

@router.get("/teacher/content", response_class=HTMLResponse)
def teacher_content_center(request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    grade_groups, course_map, stats, schedule_map, schedule_stats = _content_center_payload(db)
    return render_template("teacher_content_center.html", ctx(request, db, user=u, grade_groups=grade_groups, course_map=course_map, stats=stats, schedule_map=schedule_map, schedule_stats=schedule_stats, now=datetime.utcnow()))

@router.post("/teacher/content/unit")
def teacher_content_unit_create(request: Request, course_id: int = Form(...), name: str = Form(...), description: str = Form(""), order_index: int = Form(1), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    course = db.get(Course, course_id)
    if not course: raise HTTPException(404)
    clean = name.strip()
    if not clean: raise HTTPException(400, "اسم الوحدة مطلوب")
    exists = db.query(ContentUnit).filter(ContentUnit.course_id == course_id, func.lower(ContentUnit.name) == clean.lower()).first()
    if exists: raise HTTPException(400, "الوحدة موجودة بالفعل")
    unit = ContentUnit(course_id=course_id, name=clean[:180], description=description.strip()[:2000], order_index=max(1, min(order_index, 999)))
    db.add(unit); db.commit(); audit(db, request, u, "content_unit_created", {"unit_id": unit.id, "course_id": course_id})
    return RedirectResponse(f"/teacher/content#course-{course_id}", 303)

@router.post("/teacher/content/unit/{unit_id}/toggle")
def teacher_content_unit_toggle(unit_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    unit = db.get(ContentUnit, unit_id)
    if not unit: raise HTTPException(404)
    unit.published = not unit.published; db.commit(); audit(db, request, u, "content_unit_toggled", {"unit_id": unit.id, "published": unit.published})
    return RedirectResponse(f"/teacher/content#course-{unit.course_id}", 303)

@router.post("/teacher/content/assign")
def teacher_content_assign(request: Request, content_type: str = Form(...), content_id: int = Form(...), unit_id: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    spec = {
        "lesson": (Lesson, LessonUnitAssignment, "lesson_id"),
        "quiz": (Quiz, QuizUnitAssignment, "quiz_id"),
        "homework": (Homework, HomeworkUnitAssignment, "homework_id"),
    }.get(content_type)
    if not spec: raise HTTPException(400)
    model, assign_model, id_field = spec
    item = db.get(model, content_id)
    if not item: raise HTTPException(404)
    current = db.query(assign_model).filter(getattr(assign_model, id_field) == content_id).first()
    if unit_id:
        unit = db.get(ContentUnit, unit_id)
        if not unit or unit.course_id != item.course_id: raise HTTPException(400, "الوحدة لا تنتمي لنفس الكورس")
        if current: current.unit_id = unit.id
        else: db.add(assign_model(**{id_field: content_id, "unit_id": unit.id}))
    elif current:
        db.delete(current)
    db.commit(); audit(db, request, u, "content_unit_assigned", {"type": content_type, "content_id": content_id, "unit_id": unit_id})
    return RedirectResponse(f"/teacher/content#course-{item.course_id}", 303)

def _clone_quiz(db: Session, source: Quiz, target_course_id: int, title_suffix: str = "") -> Quiz:
    clone = Quiz(course_id=target_course_id, title=(source.title + title_suffix)[:180], published=False,
                 time_limit_minutes=source.time_limit_minutes, max_attempts=source.max_attempts,
                 shuffle_questions=source.shuffle_questions)
    db.add(clone); db.flush()
    questions = db.query(Question).filter(Question.quiz_id == source.id).order_by(Question.id).all()
    for pos, q in enumerate(questions, 1):
        nq = Question(quiz_id=clone.id, text=q.text, option_a=q.option_a, option_b=q.option_b,
                      option_c=q.option_c, option_d=q.option_d, correct=q.correct)
        db.add(nq); db.flush()
        setting = db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id == q.id).first()
        db.add(QuizQuestionSetting(question_id=nq.id, position=setting.position if setting else pos,
                                   points=setting.points if setting else 1))
    return clone

def _clone_unit_contents(db: Session, source_unit: ContentUnit, target_course_id: int, target_unit: ContentUnit):
    lesson_map = {}
    lesson_ids = [x.lesson_id for x in db.query(LessonUnitAssignment).filter(LessonUnitAssignment.unit_id == source_unit.id).all()]
    for lesson in db.query(Lesson).filter(Lesson.id.in_(lesson_ids or [-1])).order_by(Lesson.order_index, Lesson.id).all():
        nl = Lesson(course_id=target_course_id, title=lesson.title, body=lesson.body, video_url=lesson.video_url,
                    order_index=lesson.order_index, published=False)
        db.add(nl); db.flush(); lesson_map[lesson.id] = nl.id
        db.add(LessonUnitAssignment(lesson_id=nl.id, unit_id=target_unit.id))
        vp = db.query(LessonVideoProfile).filter(LessonVideoProfile.lesson_id == lesson.id).first()
        if vp:
            db.add(LessonVideoProfile(lesson_id=nl.id, provider=vp.provider, stream_type=vp.stream_type,
                drm_mode=vp.drm_mode, processing_status=vp.processing_status, thumbnail_url=vp.thumbnail_url,
                duration_seconds=vp.duration_seconds))
        dr = db.query(LessonDripRule).filter_by(lesson_id=lesson.id).first()
        if dr:
            db.add(LessonDripRule(lesson_id=nl.id, mode=dr.mode, delay_days=dr.delay_days, enabled=dr.enabled))
    quiz_ids = [x.quiz_id for x in db.query(QuizUnitAssignment).filter(QuizUnitAssignment.unit_id == source_unit.id).all()]
    for quiz in db.query(Quiz).filter(Quiz.id.in_(quiz_ids or [-1])).order_by(Quiz.id).all():
        nq = _clone_quiz(db, quiz, target_course_id)
        db.add(QuizUnitAssignment(quiz_id=nq.id, unit_id=target_unit.id))
    hw_ids = [x.homework_id for x in db.query(HomeworkUnitAssignment).filter(HomeworkUnitAssignment.unit_id == source_unit.id).all()]
    for hw in db.query(Homework).filter(Homework.id.in_(hw_ids or [-1])).order_by(Homework.id).all():
        nhw = Homework(course_id=target_course_id, lesson_id=lesson_map.get(hw.lesson_id), title=hw.title,
                       instructions=hw.instructions, due_at=None, published=False)
        db.add(nhw); db.flush(); db.add(HomeworkUnitAssignment(homework_id=nhw.id, unit_id=target_unit.id))
    return lesson_map

@router.post("/teacher/content/schedule")
def teacher_content_schedule(request: Request, content_type: str = Form(...), content_id: int = Form(...), starts_at: str = Form(""), ends_at: str = Form(""), enabled: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    model = {"unit": ContentUnit, "lesson": Lesson, "quiz": Quiz, "homework": Homework}.get(content_type)
    if not model: raise HTTPException(400, "نوع المحتوى غير صالح")
    item = db.get(model, content_id)
    if not item: raise HTTPException(404)
    def parse_dt(value: str):
        value=(value or "").strip()
        if not value: return None
        try: return datetime.fromisoformat(value)
        except ValueError: raise HTTPException(400, "التاريخ أو الوقت غير صالح")
    start=parse_dt(starts_at); end=parse_dt(ends_at)
    if start and end and end <= start: raise HTTPException(400, "وقت الإخفاء يجب أن يكون بعد وقت الظهور")
    row=target_schedule(db, content_type, content_id)
    if not row:
        row=ContentSchedule(content_type=content_type, content_id=content_id); db.add(row)
    row.starts_at=start; row.ends_at=end; row.enabled=bool(enabled)
    db.commit(); audit(db, request, u, "content_schedule_updated", {"content_type": content_type, "content_id": content_id, "starts_at": starts_at, "ends_at": ends_at, "enabled": bool(enabled)})
    course_id = item.course_id if hasattr(item, "course_id") else 0
    return RedirectResponse(f"/teacher/content#course-{course_id}", 303)

@router.post("/teacher/content/course/{course_id}/period")
def teacher_content_period_update(course_id: int, request: Request, academic_year: str = Form(...), term: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    course = db.get(Course, course_id)
    if not course: raise HTTPException(404)
    year = academic_year.strip()[:20]; term_clean = term.strip()[:30]
    if not year or not term_clean: raise HTTPException(400, "السنة الدراسية والترم مطلوبان")
    row = db.query(CourseAcademicPeriod).filter(CourseAcademicPeriod.course_id == course_id).first()
    if row: row.academic_year, row.term = year, term_clean
    else: db.add(CourseAcademicPeriod(course_id=course_id, academic_year=year, term=term_clean))
    db.commit(); audit(db, request, u, "course_period_updated", {"course_id": course_id, "academic_year": year, "term": term_clean})
    return RedirectResponse(f"/teacher/content#course-{course_id}", 303)

@router.post("/teacher/content/unit/{unit_id}/clone")
def teacher_content_unit_clone(unit_id: int, request: Request, target_course_id: int = Form(...), new_name: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    source = db.get(ContentUnit, unit_id); target_course = db.get(Course, target_course_id)
    if not source or not target_course: raise HTTPException(404)
    name = (new_name.strip() or f"{source.name} - نسخة")[:180]
    base=name; idx=2
    while db.query(ContentUnit).filter(ContentUnit.course_id == target_course_id, func.lower(ContentUnit.name) == name.lower()).first():
        name=f"{base} {idx}"[:180]; idx += 1
    target = ContentUnit(course_id=target_course_id, name=name, description=source.description,
                         order_index=source.order_index, published=False)
    db.add(target); db.flush(); _clone_unit_contents(db, source, target_course_id, target)
    db.commit(); audit(db, request, u, "content_unit_cloned", {"source_unit_id": unit_id, "target_unit_id": target.id, "target_course_id": target_course_id})
    return RedirectResponse(f"/teacher/content#course-{target_course_id}", 303)

@router.post("/teacher/content/course/{course_id}/clone")
def teacher_content_course_clone(course_id: int, request: Request, academic_year: str = Form(...), term: str = Form(...), new_title: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    source = db.get(Course, course_id)
    if not source: raise HTTPException(404)
    title=(new_title.strip() or f"{source.title} - {academic_year.strip()}")[:180]
    target=Course(title=title, description=source.description, grade=source.grade, price=source.price, published=False, teacher_id=source.teacher_id)
    db.add(target); db.flush()
    db.add(CourseAcademicPeriod(course_id=target.id, academic_year=academic_year.strip()[:20], term=term.strip()[:30]))
    units=db.query(ContentUnit).filter(ContentUnit.course_id == source.id).order_by(ContentUnit.order_index, ContentUnit.id).all()
    for unit in units:
        nu=ContentUnit(course_id=target.id, name=unit.name, description=unit.description, order_index=unit.order_index, published=False)
        db.add(nu); db.flush(); _clone_unit_contents(db, unit, target.id, nu)
    # Clone unassigned lessons/quizzes/homeworks too so the course copy is complete.
    assigned_lesson_ids={x.lesson_id for x in db.query(LessonUnitAssignment).join(ContentUnit, LessonUnitAssignment.unit_id == ContentUnit.id).filter(ContentUnit.course_id == source.id).all()}
    loose_map={}
    for lesson in db.query(Lesson).filter(Lesson.course_id == source.id).order_by(Lesson.order_index, Lesson.id).all():
        if lesson.id in assigned_lesson_ids: continue
        nl=Lesson(course_id=target.id, title=lesson.title, body=lesson.body, video_url=lesson.video_url, order_index=lesson.order_index, published=False)
        db.add(nl); db.flush(); loose_map[lesson.id]=nl.id
    assigned_quiz_ids={x.quiz_id for x in db.query(QuizUnitAssignment).join(ContentUnit, QuizUnitAssignment.unit_id == ContentUnit.id).filter(ContentUnit.course_id == source.id).all()}
    for quiz in db.query(Quiz).filter(Quiz.course_id == source.id).all():
        if quiz.id not in assigned_quiz_ids: _clone_quiz(db, quiz, target.id)
    assigned_hw_ids={x.homework_id for x in db.query(HomeworkUnitAssignment).join(ContentUnit, HomeworkUnitAssignment.unit_id == ContentUnit.id).filter(ContentUnit.course_id == source.id).all()}
    for hw in db.query(Homework).filter(Homework.course_id == source.id).all():
        if hw.id in assigned_hw_ids: continue
        db.add(Homework(course_id=target.id, lesson_id=loose_map.get(hw.lesson_id), title=hw.title, instructions=hw.instructions, due_at=None, published=False))
    db.commit(); audit(db, request, u, "course_cloned_for_academic_period", {"source_course_id": source.id, "target_course_id": target.id, "academic_year": academic_year, "term": term})
    return RedirectResponse(f"/teacher/content#course-{target.id}", 303)

@router.get("/teacher/revision", response_class=HTMLResponse)
def teacher_revision_center(request: Request, db: Session = Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    plans=db.query(RevisionPlan).order_by(RevisionPlan.exam_date.asc().nullslast(), RevisionPlan.id.desc()).all()
    tasks=db.query(RevisionTask).order_by(RevisionTask.plan_id,RevisionTask.day_number,RevisionTask.order_index,RevisionTask.id).all()
    by_plan={}
    for t in tasks: by_plan.setdefault(t.plan_id,[]).append(t)
    courses=db.query(Course).order_by(Course.grade,Course.title).all()
    lessons=db.query(Lesson).order_by(Lesson.course_id,Lesson.order_index).all()
    quizzes=db.query(Quiz).order_by(Quiz.course_id,Quiz.id).all()
    homeworks=db.query(Homework).order_by(Homework.course_id,Homework.id).all()
    completed=db.query(RevisionTaskProgress).filter(RevisionTaskProgress.completed==True).count()
    return render_template("teacher_revision.html",ctx(request,db,user=u,plans=plans,tasks_by_plan=by_plan,courses=courses,lessons=lessons,quizzes=quizzes,homeworks=homeworks,completed_count=completed,now=datetime.utcnow()))

@router.post("/teacher/revision/plan")
def teacher_revision_plan_create(request:Request,title:str=Form(...),description:str=Form(""),grade:str=Form("الصف الثالث الثانوي"),start_date:str=Form(""),exam_date:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    def p(v):
        if not v.strip(): return None
        try:return datetime.fromisoformat(v.strip())
        except ValueError: raise HTTPException(400,"تاريخ غير صالح")
    row=RevisionPlan(title=title.strip()[:180],description=description.strip(),grade=grade.strip()[:80],start_date=p(start_date),exam_date=p(exam_date),published=False,created_by=u.id)
    db.add(row);db.commit();audit(db,request,u,"revision_plan_created",{"plan_id":row.id,"grade":row.grade})
    return RedirectResponse(f"/teacher/revision#plan-{row.id}",303)

@router.post("/teacher/revision/plan/{plan_id}/toggle")
def teacher_revision_plan_toggle(plan_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    row=db.get(RevisionPlan,plan_id)
    if not row: raise HTTPException(404)
    row.published=not row.published;db.commit();audit(db,request,u,"revision_plan_publish_toggled",{"plan_id":row.id,"published":row.published})
    return RedirectResponse(f"/teacher/revision#plan-{row.id}",303)

@router.post("/teacher/revision/task")
def teacher_revision_task_create(request:Request,plan_id:int=Form(...),day_number:int=Form(1),order_index:int=Form(1),title:str=Form(...),description:str=Form(""),content_type:str=Form("note"),content_id:int=Form(0),due_at:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    plan=db.get(RevisionPlan,plan_id)
    if not plan: raise HTTPException(404)
    if content_type not in {"note","lesson","quiz","homework"}: raise HTTPException(400,"نوع المهمة غير صالح")
    cid=content_id or None
    if cid and not revision_target(db, RevisionTask(content_type=content_type,content_id=cid,plan_id=plan_id,title="")): raise HTTPException(404,"المحتوى غير موجود")
    due=None
    if due_at.strip():
        try: due=datetime.fromisoformat(due_at.strip())
        except ValueError: raise HTTPException(400,"موعد المهمة غير صالح")
    row=RevisionTask(plan_id=plan_id,day_number=max(1,day_number),order_index=max(1,order_index),title=title.strip()[:180],description=description.strip(),content_type=content_type,content_id=cid,due_at=due)
    db.add(row);db.commit();audit(db,request,u,"revision_task_created",{"plan_id":plan_id,"task_id":row.id,"content_type":content_type})
    return RedirectResponse(f"/teacher/revision#plan-{plan_id}",303)

@router.post("/teacher/revision/task/{task_id}/delete")
def teacher_revision_task_delete(task_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    row=db.get(RevisionTask,task_id)
    if not row: raise HTTPException(404)
    pid=row.plan_id; db.query(RevisionTaskProgress).filter_by(task_id=row.id).delete();db.delete(row);db.commit();audit(db,request,u,"revision_task_deleted",{"task_id":task_id})
    return RedirectResponse(f"/teacher/revision#plan-{pid}",303)

@router.get("/revision", response_class=HTMLResponse)
def student_revision_plans(request:Request,db:Session=Depends(get_db)):
    u=require_user(request,db)
    if u.role!="student": return RedirectResponse("/dashboard",302)
    profile=db.query(StudentProfile).filter_by(user_id=u.id).first()
    grade=(profile.grade if profile and profile.grade else "").strip()
    q=db.query(RevisionPlan).filter(RevisionPlan.published==True)
    if grade: q=q.filter(or_(RevisionPlan.grade==grade,RevisionPlan.grade=="كل الصفوف"))
    plans=q.order_by(RevisionPlan.exam_date.asc().nullslast(),RevisionPlan.id.desc()).all()
    tasks=db.query(RevisionTask).filter(RevisionTask.plan_id.in_([p.id for p in plans] or [-1])).order_by(RevisionTask.day_number,RevisionTask.order_index).all()
    progress={x.task_id:x for x in db.query(RevisionTaskProgress).filter_by(user_id=u.id,completed=True).all()}
    rows=[]
    for p in plans:
        pt=[t for t in tasks if t.plan_id==p.id]
        done=sum(1 for t in pt if t.id in progress); pct=round(done*100/len(pt)) if pt else 0
        for t in pt:
            t.target_url=revision_target_url(t); t.target=revision_target(db,t)
        rows.append({"plan":p,"tasks":pt,"done":done,"total":len(pt),"pct":pct,"completed_ids":set(progress.keys())})
    return render_template("student_revision.html",ctx(request,db,user=u,rows=rows,now=datetime.utcnow()))

@router.post("/revision/task/{task_id}/toggle")
def student_revision_task_toggle(task_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_user(request,db)
    if u.role!="student": raise HTTPException(403)
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    task=db.get(RevisionTask,task_id); plan=db.get(RevisionPlan,task.plan_id) if task else None
    if not task or not plan or not plan.published: raise HTTPException(404)
    profile=db.query(StudentProfile).filter_by(user_id=u.id).first(); grade=(profile.grade if profile else "") or ""
    if plan.grade not in {"كل الصفوف",grade}: raise HTTPException(403)
    _pg_xact_lock(db, 5521, (int(u.id) * 1000003 + int(task.id)))
    row=db.query(RevisionTaskProgress).filter_by(user_id=u.id,task_id=task.id).with_for_update().first()
    if not row: row=RevisionTaskProgress(user_id=u.id,task_id=task.id,completed=True,completed_at=datetime.utcnow());db.add(row)
    else:
        row.completed=not row.completed; row.completed_at=datetime.utcnow() if row.completed else None
    db.commit()
    return RedirectResponse("/revision",303)
