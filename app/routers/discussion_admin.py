from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Course, DiscussionPost, Lesson
from ..permissions import can_manage_course
from ..request_context import audit, require_role
from ..security import check_csrf
router=APIRouter()

@router.post('/admin/discussion/{post_id}/toggle')
def discussion_toggle(post_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,'super_admin','admin','content_manager')
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    post=db.get(DiscussionPost,post_id); lesson=db.get(Lesson,post.lesson_id) if post else None; course=db.get(Course,lesson.course_id) if lesson else None
    if not post or not course or not can_manage_course(u.role): raise HTTPException(403)
    post.status='hidden' if post.status=='visible' else 'visible'; db.commit(); audit(db,request,u,'discussion_moderated',{'post_id':post.id})
    return RedirectResponse(f'/lesson/{lesson.id}#discussion',303)
