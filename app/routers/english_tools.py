from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import PointLedger, VocabularyItem, VocabularyReview
from ..request_context import require_role, template_context as ctx
from ..security import check_csrf
from ..services.dashboard_experience import points_total
from ..services.student_rewards import touch_student_streak
from ..services.template_rendering import render_template
router=APIRouter()

@router.get('/english-tools', response_class=HTMLResponse)
def english_tools(request: Request, db: Session=Depends(get_db)):
    u=require_role(request,db,'student'); streak=touch_student_streak(db,u.id); now=datetime.utcnow()
    due=(db.query(VocabularyItem,VocabularyReview).join(VocabularyReview,VocabularyReview.vocabulary_id==VocabularyItem.id)
         .filter(VocabularyReview.user_id==u.id,VocabularyReview.next_review_at<=now).limit(20).all())
    if not due:
        known={r.vocabulary_id for r in db.query(VocabularyReview).filter_by(user_id=u.id).all()}
        items=db.query(VocabularyItem).filter(~VocabularyItem.id.in_(known) if known else True).limit(20).all(); due=[(x,None) for x in items]
    return render_template('english_tools.html',ctx(request,db,due=due,streak=streak,points=points_total(db,u.id)))

@router.post('/english-tools/review/{vocab_id}')
def review_vocabulary(vocab_id:int, request:Request, result:str=Form(...), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,'student')
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    item=db.get(VocabularyItem,vocab_id)
    if not item: raise HTTPException(404)
    row=db.query(VocabularyReview).filter_by(user_id=u.id,vocabulary_id=vocab_id).first()
    if not row: row=VocabularyReview(user_id=u.id,vocabulary_id=vocab_id); db.add(row)
    good=result=='correct'
    if good: row.correct_count+=1; row.streak+=1; row.box=min(6,row.box+1)
    else: row.wrong_count+=1; row.streak=0; row.box=1
    delays=[0,1,3,7,14,30,60]; row.next_review_at=datetime.utcnow()+timedelta(days=delays[row.box])
    db.add(PointLedger(user_id=u.id,points=5 if good else 1,reason='vocabulary_review',ref_type='vocabulary',ref_id=vocab_id))
    touch_student_streak(db,u.id); db.commit(); return RedirectResponse('/english-tools',303)
