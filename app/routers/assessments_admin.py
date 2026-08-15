import random
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import *
from ..permissions import can_manage_course
from ..request_context import require_role, audit, template_context as ctx
from ..security import check_csrf
from ..services.template_rendering import render_template

router = APIRouter()
@router.post("/admin/course/{course_id}/quizzes")
def add_quiz(course_id: int, request: Request, title: str = Form(...), time_limit_minutes: int = Form(30), max_attempts: int = Form(1), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c or not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    quiz = Quiz(course_id=course_id, title=title.strip(), time_limit_minutes=max(1,time_limit_minutes), max_attempts=max(1,max_attempts), published=False)
    db.add(quiz); db.commit(); audit(db, request, u, "quiz_created", {"quiz_id": quiz.id})
    return RedirectResponse(f"/admin/quiz/{quiz.id}", 303)


@router.get("/teacher/mock-exams", response_class=HTMLResponse)
def teacher_mock_exams(request: Request, db: Session = Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    courses=db.query(Course).order_by(Course.grade,Course.title).all()
    units=db.query(ContentUnit).order_by(ContentUnit.course_id,ContentUnit.order_index).all()
    profiles=db.query(MockExamProfile).order_by(MockExamProfile.id.desc()).all()
    quiz_map={q.id:q for q in db.query(Quiz).filter(Quiz.id.in_([p.quiz_id for p in profiles] or [-1])).all()}
    return render_template("teacher_mock_exams.html",ctx(request,db,user=u,courses=courses,units=units,profiles=profiles,quiz_map=quiz_map))

@router.post("/teacher/mock-exams")
def create_mock_exam(request:Request, course_id:int=Form(...), title:str=Form(...), question_count:int=Form(20), time_limit_minutes:int=Form(60), unit_id:int=Form(0), difficulty:str=Form("all"), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    course=db.get(Course,course_id)
    if not course or not can_manage_course(u.role,teacher_id=course.teacher_id,user_id=u.id): raise HTTPException(403)
    unit=db.get(ContentUnit,unit_id) if unit_id else None
    if unit and unit.course_id != course.id: raise HTTPException(400,"الوحدة لا تتبع الكورس")
    difficulty=difficulty if difficulty in {"all","easy","medium","hard"} else "all"
    question_count=max(1,min(100,question_count)); time_limit_minutes=max(1,min(300,time_limit_minutes))
    bank=db.query(QuestionBankItem).filter_by(course_id=course.id).all()
    tax_map={x.bank_item_id:x for x in db.query(QuestionBankTaxonomy).filter(QuestionBankTaxonomy.bank_item_id.in_([b.id for b in bank] or [-1])).all()}
    eligible=[]
    for item in bank:
        tax=tax_map.get(item.id)
        if unit and (not tax or tax.unit_id != unit.id): continue
        if difficulty != "all" and (not tax or tax.difficulty != difficulty): continue
        eligible.append(item)
    if len(eligible) < question_count: raise HTTPException(400,f"بنك الأسئلة يحتوي على {len(eligible)} سؤالًا مطابقًا فقط")
    random.shuffle(eligible); chosen=eligible[:question_count]
    quiz=Quiz(course_id=course.id,title=title.strip() or "امتحان تجريبي",published=False,time_limit_minutes=time_limit_minutes,max_attempts=1,shuffle_questions=True)
    db.add(quiz); db.flush(); db.add(MockExamProfile(quiz_id=quiz.id,source_unit_id=unit.id if unit else None,difficulty_filter=difficulty,requested_questions=question_count))
    if unit: db.add(QuizUnitAssignment(quiz_id=quiz.id,unit_id=unit.id))
    for pos,item in enumerate(chosen,1):
        q=Question(quiz_id=quiz.id,text=item.text,option_a=item.option_a,option_b=item.option_b,option_c=item.option_c,option_d=item.option_d,correct=item.correct)
        db.add(q); db.flush(); db.add(QuizQuestionSetting(question_id=q.id,position=pos,points=item.default_points))
        tax=tax_map.get(item.id)
        if tax: db.add(QuestionTaxonomy(question_id=q.id,unit_id=tax.unit_id,difficulty=tax.difficulty))
    db.commit(); audit(db,request,u,"mock_exam_created",{"quiz_id":quiz.id,"questions":question_count,"difficulty":difficulty,"unit_id":unit.id if unit else None})
    return RedirectResponse(f"/admin/quiz/{quiz.id}",303)

@router.get("/admin/quiz/{quiz_id}", response_class=HTMLResponse)
def admin_quiz(quiz_id: int, request: Request, db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    quiz = db.get(Quiz, quiz_id)
    if not quiz: raise HTTPException(404)
    course = db.get(Course, quiz.course_id)
    if not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    questions = db.query(Question).filter_by(quiz_id=quiz.id).all()
    settings = {x.question_id:x for x in db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id.in_([q.id for q in questions] or [-1])).all()}
    questions.sort(key=lambda q: (settings.get(q.id).position if settings.get(q.id) else q.id, q.id))
    bank_items = db.query(QuestionBankItem).filter_by(course_id=course.id).order_by(QuestionBankItem.id.desc()).limit(100).all()
    bank_tax = {x.bank_item_id:x for x in db.query(QuestionBankTaxonomy).filter(QuestionBankTaxonomy.bank_item_id.in_([b.id for b in bank_items] or [-1])).all()}
    units = db.query(ContentUnit).filter_by(course_id=course.id).order_by(ContentUnit.order_index, ContentUnit.id).all()
    total_points = sum((settings.get(q.id).points if settings.get(q.id) else 1) for q in questions)
    return render_template("admin_quiz.html", ctx(request, db, quiz=quiz, course=course, questions=questions, settings=settings, bank_items=bank_items, bank_tax=bank_tax, units=units, total_points=total_points))

@router.post("/admin/quiz/{quiz_id}/questions")
def add_question(quiz_id: int, request: Request, text: str = Form(...), option_a: str = Form(...), option_b: str = Form(...), option_c: str = Form(...), option_d: str = Form(...), correct: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    quiz = db.get(Quiz, quiz_id)
    if not quiz: raise HTTPException(404)
    course = db.get(Course, quiz.course_id)
    if not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    correct = correct.upper()
    if correct not in {"A","B","C","D"}: raise HTTPException(400)
    q = Question(quiz_id=quiz.id, text=text.strip(), option_a=option_a.strip(), option_b=option_b.strip(), option_c=option_c.strip(), option_d=option_d.strip(), correct=correct)
    db.add(q); db.flush()
    pos = db.query(QuizQuestionSetting).join(Question, QuizQuestionSetting.question_id == Question.id).filter(Question.quiz_id == quiz.id).count() + 1
    db.add(QuizQuestionSetting(question_id=q.id, position=pos, points=1))
    db.commit(); audit(db, request, u, "question_created", {"quiz_id": quiz.id, "question_id": q.id})
    return RedirectResponse(f"/admin/quiz/{quiz.id}", 303)

@router.post("/admin/quiz/{quiz_id}/settings")
def update_quiz_settings(quiz_id: int, request: Request, time_limit_minutes: int = Form(30), max_attempts: int = Form(1), shuffle_questions: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    quiz = db.get(Quiz, quiz_id); course = db.get(Course, quiz.course_id) if quiz else None
    if not quiz or not course or not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    quiz.time_limit_minutes=max(1,min(300,time_limit_minutes)); quiz.max_attempts=max(1,min(20,max_attempts)); quiz.shuffle_questions = shuffle_questions == "on"
    db.commit(); audit(db, request, u, "quiz_settings_updated", {"quiz_id":quiz.id})
    return RedirectResponse(f"/admin/quiz/{quiz.id}",303)

@router.post("/admin/quiz/{quiz_id}/bank")
def add_bank_item(quiz_id: int, request: Request, text: str = Form(...), option_a: str = Form(...), option_b: str = Form(...), option_c: str = Form(...), option_d: str = Form(...), correct: str = Form(...), points: int = Form(1), unit_id: int = Form(0), difficulty: str = Form("medium"), csrf: str = Form(...), db: Session = Depends(get_db)):
    u=require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    quiz=db.get(Quiz,quiz_id); course=db.get(Course,quiz.course_id) if quiz else None
    if not quiz or not course or not can_manage_course(u.role,teacher_id=course.teacher_id,user_id=u.id): raise HTTPException(403)
    correct=correct.upper();
    if correct not in {"A","B","C","D"}: raise HTTPException(400)
    item=QuestionBankItem(course_id=course.id,created_by=u.id,text=text.strip(),option_a=option_a.strip(),option_b=option_b.strip(),option_c=option_c.strip(),option_d=option_d.strip(),correct=correct,default_points=max(1,min(100,points)))
    db.add(item); db.flush()
    difficulty = difficulty if difficulty in {"easy","medium","hard"} else "medium"
    valid_unit = db.get(ContentUnit, unit_id) if unit_id else None
    if valid_unit and valid_unit.course_id != course.id: valid_unit = None
    db.add(QuestionBankTaxonomy(bank_item_id=item.id, unit_id=valid_unit.id if valid_unit else None, difficulty=difficulty))
    db.commit(); audit(db,request,u,"question_bank_created",{"quiz_id":quiz.id,"bank_id":item.id,"difficulty":difficulty,"unit_id":valid_unit.id if valid_unit else None})
    return RedirectResponse(f"/admin/quiz/{quiz.id}",303)

@router.post("/admin/quiz/{quiz_id}/bank/{bank_id}/use")
def use_bank_item(quiz_id:int, bank_id:int, request:Request, csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    quiz=db.get(Quiz,quiz_id); course=db.get(Course,quiz.course_id) if quiz else None; item=db.get(QuestionBankItem,bank_id)
    if not quiz or not course or not item or item.course_id!=course.id or not can_manage_course(u.role,teacher_id=course.teacher_id,user_id=u.id): raise HTTPException(403)
    q=Question(quiz_id=quiz.id,text=item.text,option_a=item.option_a,option_b=item.option_b,option_c=item.option_c,option_d=item.option_d,correct=item.correct)
    db.add(q); db.flush(); pos=db.query(Question).filter_by(quiz_id=quiz.id).count(); db.add(QuizQuestionSetting(question_id=q.id,position=pos,points=item.default_points))
    tax=db.query(QuestionBankTaxonomy).filter_by(bank_item_id=item.id).first()
    if tax: db.add(QuestionTaxonomy(question_id=q.id, unit_id=tax.unit_id, difficulty=tax.difficulty))
    db.commit()
    return RedirectResponse(f"/admin/quiz/{quiz.id}",303)

@router.post("/admin/question/{question_id}/meta")
def update_question_meta(question_id:int, request:Request, position:int=Form(1), points:int=Form(1), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    q=db.get(Question,question_id); quiz=db.get(Quiz,q.quiz_id) if q else None; course=db.get(Course,quiz.course_id) if quiz else None
    if not q or not quiz or not course or not can_manage_course(u.role,teacher_id=course.teacher_id,user_id=u.id): raise HTTPException(403)
    meta=db.query(QuizQuestionSetting).filter_by(question_id=q.id).first()
    if not meta: meta=QuizQuestionSetting(question_id=q.id); db.add(meta)
    meta.position=max(1,position); meta.points=max(1,min(100,points)); db.commit()
    return RedirectResponse(f"/admin/quiz/{quiz.id}",303)

@router.get("/admin/quiz/{quiz_id}/preview", response_class=HTMLResponse)
def preview_quiz(quiz_id:int, request:Request, db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    quiz=db.get(Quiz,quiz_id); course=db.get(Course,quiz.course_id) if quiz else None
    if not quiz or not course or not can_manage_course(u.role,teacher_id=course.teacher_id,user_id=u.id): raise HTTPException(403)
    qs=db.query(Question).filter_by(quiz_id=quiz.id).all(); settings={x.question_id:x for x in db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id.in_([q.id for q in qs] or [-1])).all()}; qs.sort(key=lambda q:(settings.get(q.id).position if settings.get(q.id) else q.id,q.id))
    return render_template("admin_quiz_preview.html", ctx(request,db,quiz=quiz,course=course,questions=qs,settings=settings,total_points=sum((settings.get(q.id).points if settings.get(q.id) else 1) for q in qs)))

@router.post("/admin/question/{question_id}/delete")
def delete_question(question_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    q = db.get(Question, question_id)
    if not q: raise HTTPException(404)
    quiz = db.get(Quiz, q.quiz_id); course = db.get(Course, quiz.course_id)
    if not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    if quiz.published: raise HTTPException(409, "أوقف نشر الاختبار قبل حذف الأسئلة")
    db.delete(q); db.commit(); audit(db, request, u, "question_deleted", {"question_id": question_id, "quiz_id": quiz.id})
    return RedirectResponse(f"/admin/quiz/{quiz.id}", 303)

@router.post("/admin/quiz/{quiz_id}/toggle")
def toggle_quiz(quiz_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    quiz = db.get(Quiz, quiz_id)
    if not quiz: raise HTTPException(404)
    course = db.get(Course, quiz.course_id)
    if not can_manage_course(u.role, teacher_id=course.teacher_id, user_id=u.id): raise HTTPException(403)
    if not quiz.published and db.query(Question).filter_by(quiz_id=quiz.id).count() == 0:
        raise HTTPException(400, "لا يمكن نشر اختبار بدون أسئلة")
    quiz.published = not quiz.published; db.commit()
    audit(db, request, u, "quiz_publish_toggled", {"quiz_id": quiz.id, "published": quiz.published})
    return RedirectResponse(f"/admin/quiz/{quiz.id}", 303)
@router.post("/admin/course/{course_id}/homework")
def create_homework(course_id: int, request: Request, title: str = Form(...), instructions: str = Form(""), lesson_id: int | None = Form(None), due_at: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    c = db.get(Course, course_id)
    if not c or not can_manage_course(u.role, teacher_id=c.teacher_id, user_id=u.id): raise HTTPException(403)
    if lesson_id:
        l = db.get(Lesson, lesson_id)
        if not l or l.course_id != c.id: raise HTTPException(400)
    parsed_due = None
    if due_at.strip():
        try:
            parsed_due = datetime.fromisoformat(due_at.strip())
        except ValueError:
            raise HTTPException(400, "موعد تسليم الواجب غير صالح")
    h = Homework(course_id=c.id, lesson_id=lesson_id, title=title.strip()[:180], instructions=instructions.strip(), due_at=parsed_due, published=True)
    db.add(h); db.commit(); audit(db, request, u, "homework_created", {"homework_id": h.id, "course_id": c.id})
    return RedirectResponse(f"/admin/course/{c.id}", 303)



@router.post("/admin/homework/{homework_id}/grade")
def grade_homework(homework_id: int, request: Request, student_id: int = Form(...), score: float = Form(...), feedback: str = Form(""), return_to: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    h = db.get(Homework, homework_id); c = db.get(Course, h.course_id) if h else None
    if not h or not c or not can_manage_course(u.role): raise HTTPException(403)
    sub = db.query(HomeworkSubmission).filter_by(homework_id=h.id, student_id=student_id).first()
    if not sub: raise HTTPException(404)
    sub.score=max(0,min(100,score)); sub.feedback=feedback.strip(); sub.status="graded"; sub.graded_at=datetime.utcnow(); db.commit()
    db.add(Notification(user_id=student_id, title="تم تصحيح الواجب", body=f"{h.title}: {sub.score:.0f}/100", kind="success")); db.commit()
    if return_to == "assessment":
        return RedirectResponse("/teacher/assessment", 303)
    return RedirectResponse(f"/admin/course/{c.id}", 303)

@router.post("/admin/homework/{homework_id}/revision")
def request_homework_revision(homework_id: int, request: Request, student_id: int = Form(...), feedback: str = Form(""), return_to: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "super_admin", "admin", "content_manager")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    h = db.get(Homework, homework_id); c = db.get(Course, h.course_id) if h else None
    if not h or not c or not can_manage_course(u.role): raise HTTPException(403)
    sub = db.query(HomeworkSubmission).filter_by(homework_id=h.id, student_id=student_id).first()
    if not sub: raise HTTPException(404)
    sub.status = "revision_requested"
    sub.feedback = feedback.strip() or "يرجى مراجعة الإجابة وإعادة التسليم."
    sub.graded_at = None
    db.add(Notification(user_id=student_id, title="مطلوب تعديل الواجب", body=f"{h.title}: {sub.feedback[:160]}", kind="warning"))
    db.commit()
    audit(db, request, u, "homework_revision_requested", {"homework_id": h.id, "student_id": student_id})
    if return_to == "assessment":
        return RedirectResponse("/teacher/assessment", 303)
    return RedirectResponse(f"/admin/course/{c.id}", 303)


