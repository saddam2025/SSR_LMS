from datetime import datetime, timedelta
import random
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import or_, text
from sqlalchemy.orm import Session
from .db import engine, get_db
from .models import Course, Enrollment, Homework, HomeworkSubmission, Lesson, LessonProgress, Notification, PointLedger, Question, Quiz, QuizAttempt, QuizQuestionSetting
from .api_v1_common import user
from .access import authorized_for_course, content_schedule_allows, lesson_access_state
from .security import check_csrf
from .services.quiz_grading import grade_answers, total_points as quiz_total_points

router = APIRouter(tags=['api-v1-learning'])

def _pg_xact_lock(db, namespace: int, entity_id: int):
    if engine.dialect.name == "postgresql":
        safe_entity = int(entity_id) & 0x7FFFFFFF
        db.execute(text("SELECT pg_advisory_xact_lock(:ns, :entity)"), {"ns": int(namespace), "entity": safe_entity})


def student(request: Request, db: Session):
    u=user(request,db)
    if u.role!='student': raise HTTPException(403,'Student account required')
    return u

def csrf(request: Request):
    if not check_csrf(request.session, request.headers.get('x-csrf-token','')): raise HTTPException(403,'CSRF failed')

def award_once(db, uid, pts, reason, ref_type, ref_id):
    if not db.query(PointLedger).filter_by(user_id=uid,reason=reason,ref_type=ref_type,ref_id=ref_id).first():
        db.add(PointLedger(user_id=uid,points=pts,reason=reason,ref_type=ref_type,ref_id=ref_id))

class QuizSubmit(BaseModel): answers: dict[str,str]
class HomeworkSubmit(BaseModel): answer_text: str

@router.get('/learning-center')
def learning_center(request:Request, db:Session=Depends(get_db)):
    u=student(request,db)
    ens=db.query(Enrollment).filter_by(user_id=u.id,active=True).all(); now=datetime.utcnow()
    course_ids=[e.course_id for e in ens if not e.expires_at or e.expires_at>now]
    quizzes=db.query(Quiz).filter(Quiz.course_id.in_(course_ids or [-1]),Quiz.published==True).order_by(Quiz.id.desc()).limit(100).all()
    quizzes=[q for q in quizzes if content_schedule_allows(db,'quiz',q.id)]
    attempts=db.query(QuizAttempt).filter(QuizAttempt.user_id==u.id,QuizAttempt.quiz_id.in_([q.id for q in quizzes] or [-1])).all()
    byq={}
    for a in attempts: byq.setdefault(a.quiz_id,[]).append(a)
    homeworks=db.query(Homework).filter(Homework.course_id.in_(course_ids or [-1]),Homework.published==True).order_by(Homework.id.desc()).limit(100).all()
    homeworks=[h for h in homeworks if content_schedule_allows(db,'homework',h.id)]
    subs={s.homework_id:s for s in db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id==u.id,HomeworkSubmission.homework_id.in_([h.id for h in homeworks] or [-1])).all()}
    return {'data':{
      'quizzes':[{'id':q.id,'title':q.title,'course_id':q.course_id,'time_limit_minutes':q.time_limit_minutes,'max_attempts':q.max_attempts,'attempts_used':len(byq.get(q.id,[])),'best_score':max([(a.score/a.total*100 if a.total else 0) for a in byq.get(q.id,[]) if a.status=='submitted'] or [None])} for q in quizzes],
      'homeworks':[{'id':h.id,'title':h.title,'course_id':h.course_id,'due_at':h.due_at.isoformat() if h.due_at else None,'status':subs[h.id].status if h.id in subs else 'pending','score':subs[h.id].score if h.id in subs else None} for h in homeworks],
      'unread_notifications':db.query(Notification).filter(Notification.user_id==u.id,Notification.read_at.is_(None)).count()
    }}

@router.get('/quizzes/{quiz_id}/attempt')
def quiz_attempt(quiz_id:int, request:Request, db:Session=Depends(get_db)):
    u=student(request,db); qz=db.get(Quiz,quiz_id)
    if not qz or not qz.published or not content_schedule_allows(db,'quiz',qz.id): raise HTTPException(404)
    if not authorized_for_course(db,u,qz.course_id): raise HTTPException(403)
    now=datetime.utcnow(); key=f'api_quiz_attempt_{quiz_id}'; attempt=None; aid=request.session.get(key)
    if aid:
        attempt=db.get(QuizAttempt,int(aid))
        if not attempt or attempt.user_id!=u.id or attempt.quiz_id!=quiz_id or attempt.status!='in_progress': attempt=None; request.session.pop(key,None)
    if attempt and attempt.started_at+timedelta(minutes=qz.time_limit_minutes)<=now:
        attempt.status='expired'; attempt.submitted_at=now; db.commit(); attempt=None; request.session.pop(key,None)
    if not attempt:
        _pg_xact_lock(db, 5507, (int(u.id) * 1000003 + int(quiz_id)))
        existing=db.query(QuizAttempt).filter_by(user_id=u.id,quiz_id=quiz_id,status='in_progress').order_by(QuizAttempt.id.desc()).with_for_update().first()
        if existing and existing.started_at+timedelta(minutes=qz.time_limit_minutes)>now: attempt=existing
        else:
            if existing:
                existing.status='expired'; existing.submitted_at=now
            used=db.query(QuizAttempt).filter_by(user_id=u.id,quiz_id=quiz_id).count()
            if used>=qz.max_attempts:
                db.commit(); raise HTTPException(403,'تم استنفاد عدد المحاولات')
            qs_for_total=db.query(Question).filter_by(quiz_id=quiz_id).all()
            attempt=QuizAttempt(quiz_id=quiz_id,user_id=u.id,total=quiz_total_points(db,qs_for_total),status='in_progress',started_at=now); db.add(attempt); db.commit(); db.refresh(attempt)
        request.session[key]=attempt.id
    qs=db.query(Question).filter_by(quiz_id=quiz_id).all()
    metas={m.question_id:m for m in db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id.in_([x.id for x in qs] or [-1])).all()}
    qs.sort(key=lambda x:(metas.get(x.id).position if metas.get(x.id) else x.id,x.id))
    if qz.shuffle_questions: random.Random(attempt.id).shuffle(qs)
    remaining=max(0,int(((attempt.started_at+timedelta(minutes=qz.time_limit_minutes))-now).total_seconds()))
    return {'data':{'quiz':{'id':qz.id,'title':qz.title},'attempt_id':attempt.id,'remaining_seconds':remaining,'questions':[{'id':q.id,'text':q.text,'options':{'A':q.option_a,'B':q.option_b,'C':q.option_c,'D':q.option_d}} for q in qs]}}

@router.post('/quizzes/{quiz_id}/submit')
def quiz_submit(quiz_id:int,payload:QuizSubmit,request:Request,db:Session=Depends(get_db)):
    u=student(request,db); csrf(request); qz=db.get(Quiz,quiz_id)
    if not qz or not qz.published or not content_schedule_allows(db,'quiz',qz.id) or not authorized_for_course(db,u,qz.course_id): raise HTTPException(403)
    key=f'api_quiz_attempt_{quiz_id}'; aid=request.session.get(key)
    _pg_xact_lock(db, 5507, (int(u.id) * 1000003 + int(quiz_id)))
    attempt=db.query(QuizAttempt).filter(QuizAttempt.id==int(aid)).with_for_update().first() if aid else None
    if not attempt or attempt.user_id!=u.id or attempt.quiz_id!=quiz_id or attempt.status!='in_progress': raise HTTPException(409,'لا توجد محاولة اختبار نشطة')
    now=datetime.utcnow()
    if attempt.started_at+timedelta(minutes=qz.time_limit_minutes)<now:
        attempt.status='expired'; attempt.submitted_at=now; db.commit(); request.session.pop(key,None); raise HTTPException(408,'انتهى وقت الاختبار')
    qs=db.query(Question).filter_by(quiz_id=quiz_id).all(); graded=grade_answers(db,qs,payload.answers)
    score=graded['score']; total=graded['total']; pct=graded['percentage']; details=graded['details']
    attempt.score=score; attempt.total=total; attempt.status='submitted'; attempt.submitted_at=now
    award_once(db,u.id,30 if pct>=80 else 15,'إنهاء اختبار','quiz_attempt',attempt.id)
    if pct>=80: db.add(Notification(user_id=u.id,title='إنجاز جديد',body=f'حصلت على {pct:.0f}% في {qz.title}',kind='success'))
    db.commit(); request.session.pop(key,None)
    return {'data':{'score':score,'total':total,'percentage':round(pct,1),'correct_count':graded['correct_count'],'question_count':graded['question_count'],'details':details}}

@router.get('/homeworks/{homework_id}')
def homework_get(homework_id:int,request:Request,db:Session=Depends(get_db)):
    u=student(request,db); h=db.get(Homework,homework_id)
    if not h or not h.published or not content_schedule_allows(db,'homework',h.id) or not authorized_for_course(db,u,h.course_id): raise HTTPException(403)
    s=db.query(HomeworkSubmission).filter_by(homework_id=h.id,student_id=u.id).first()
    return {'data':{'id':h.id,'title':h.title,'instructions':h.instructions or '','due_at':h.due_at.isoformat() if h.due_at else None,'submission':None if not s else {'answer_text':s.answer_text,'status':s.status,'score':s.score,'feedback':s.feedback or ''}}}

@router.post('/homeworks/{homework_id}/submit')
def homework_submit(homework_id:int,payload:HomeworkSubmit,request:Request,db:Session=Depends(get_db)):
    u=student(request,db); csrf(request); h=db.get(Homework,homework_id)
    if not h or not h.published or not content_schedule_allows(db,'homework',h.id) or not authorized_for_course(db,u,h.course_id): raise HTTPException(403)
    text=(payload.answer_text or '').strip()
    if len(text)<1 or len(text)>20000: raise HTTPException(400,'نص الإجابة غير صالح')
    _pg_xact_lock(db, 5506, (int(u.id) * 1000003 + int(h.id)))
    s=db.query(HomeworkSubmission).filter_by(homework_id=h.id,student_id=u.id).with_for_update().first(); first=not s or not bool(s.answer_text)
    if not s: s=HomeworkSubmission(homework_id=h.id,student_id=u.id); db.add(s)
    s.answer_text=text; s.status='submitted'; s.submitted_at=datetime.utcnow()
    if first: award_once(db,u.id,10,'تسليم واجب','homework',h.id)
    db.commit(); return {'data':{'submitted':True,'status':s.status}}

@router.post('/notifications/read-all')
def notifications_read_all(request:Request,db:Session=Depends(get_db)):
    u=student(request,db); csrf(request); now=datetime.utcnow(); db.query(Notification).filter(Notification.user_id==u.id,Notification.read_at.is_(None)).update({Notification.read_at:now}); db.commit(); return {'data':{'read_all':True}}

@router.get('/search')
def search(q:str='',request:Request=None,db:Session=Depends(get_db)):
    u=student(request,db); term=(q or '').strip()[:100]
    if not term: return {'data':{'courses':[],'lessons':[],'quizzes':[]}}
    like=f'%{term}%'; courses=[c for c in db.query(Course).filter(or_(Course.title.ilike(like),Course.description.ilike(like))).limit(30).all() if c.published and authorized_for_course(db,u,c.id)]
    lessons=[l for l in db.query(Lesson).filter(or_(Lesson.title.ilike(like),Lesson.body.ilike(like)),Lesson.published==True).limit(50).all() if authorized_for_course(db,u,l.course_id) and content_schedule_allows(db,'lesson',l.id)]
    quizzes=[z for z in db.query(Quiz).filter(Quiz.title.ilike(like),Quiz.published==True).limit(30).all() if authorized_for_course(db,u,z.course_id) and content_schedule_allows(db,'quiz',z.id)]
    return {'data':{'courses':[{'id':x.id,'title':x.title} for x in courses],'lessons':[{'id':x.id,'title':x.title,'course_id':x.course_id} for x in lessons],'quizzes':[{'id':x.id,'title':x.title,'course_id':x.course_id} for x in quizzes]}}

@router.get('/study-plan')
def study_plan(request:Request,db:Session=Depends(get_db)):
    u=student(request,db); ens=db.query(Enrollment).filter_by(user_id=u.id,active=True).all(); now=datetime.utcnow(); ids=[e.course_id for e in ens if not e.expires_at or e.expires_at>now]
    completed={p.lesson_id for p in db.query(LessonProgress).filter_by(user_id=u.id,completed=True).all()}; tasks=[]
    lessons=db.query(Lesson).filter(Lesson.course_id.in_(ids or [-1]),Lesson.published==True).order_by(Lesson.course_id,Lesson.order_index).all()
    for l in lessons:
        if l.id in completed or not content_schedule_allows(db,'lesson',l.id): continue
        access=lesson_access_state(db,u,l)
        if access['unlocked']: tasks.append({'type':'lesson','id':l.id,'title':l.title,'url':f'/student/lesson.html?id={l.id}'})
        if len(tasks)>=8: break
    hs=db.query(Homework).filter(Homework.course_id.in_(ids or [-1]),Homework.published==True).order_by(Homework.due_at.asc()).all()
    submitted={s.homework_id for s in db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id==u.id).all()}
    for h in hs:
        if h.id not in submitted and content_schedule_allows(db,'homework',h.id): tasks.append({'type':'homework','id':h.id,'title':h.title,'url':f'/student/homework.html?id={h.id}','due_at':h.due_at.isoformat() if h.due_at else None})
    pts=db.query(PointLedger).filter_by(user_id=u.id).all(); return {'data':{'tasks':tasks[:12],'points':sum(x.points for x in pts)}}
