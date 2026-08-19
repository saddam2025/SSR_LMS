from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import (User, Course, Enrollment, Notification, StudentAttendance, LiveClass, LiveClassAttendance, StudentGroup, StudentGroupMembership, GroupCourseAssignment, GroupLiveClassAssignment, CommunicationCampaign, CommunicationDelivery)
from ..request_context import audit, require_role, require_user, template_context as ctx
from ..security import check_csrf
from ..services.template_rendering import render_template
from ..services.communications import communication_recipient_ids, bulk_in_app_campaign
from ..services.community import attendance_page, student_live_classes, live_class_student_query, live_class_student_ids, live_class_students, student_group_id, group_member_ids, sync_group_course, live_class_group_id, safe_live_url

router = APIRouter()

@router.get("/admin/attendance", response_class=HTMLResponse)
def admin_attendance(request: Request, date: str="", status: str="all", page: int=1, db: Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","content_manager","support")
    try: target=datetime.strptime(date,"%Y-%m-%d").strftime("%Y-%m-%d") if date else datetime.utcnow().strftime("%Y-%m-%d")
    except ValueError: target=datetime.utcnow().strftime("%Y-%m-%d")
    if status not in {"all", "present", "absent", "excused"}: status = "all"
    rows, metrics, page, pages, filtered_total, page_size = attendance_page(db,target,status=status,page=page,page_size=100)
    return render_template("admin_attendance.html",ctx(request,db,rows=rows,metrics=metrics,target_date=target,status_filter=status,page=page,pages=pages,filtered_total=filtered_total,page_size=page_size))

@router.post("/admin/attendance/mark")
def admin_attendance_mark(request: Request, student_id:int=Form(...), attendance_date:str=Form(...), status:str=Form(...), note:str=Form(""), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager","support")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if status not in {"present","absent","excused"}: raise HTTPException(400,"حالة الحضور غير صالحة")
    try: attendance_date=datetime.strptime(attendance_date,"%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError: raise HTTPException(400,"تاريخ غير صالح")
    student = db.get(User, student_id)
    if not student or student.role != "student" or not student.is_active: raise HTTPException(404, "الطالب غير موجود أو غير نشط")
    row=db.query(StudentAttendance).filter_by(user_id=student_id,attendance_date=attendance_date).first()
    if row: row.status=status; row.note=note.strip()[:300]; row.source="manual"; row.marked_by=u.id; row.marked_at=datetime.utcnow()
    else: db.add(StudentAttendance(user_id=student_id,attendance_date=attendance_date,status=status,note=note.strip()[:300],source="manual",marked_by=u.id))
    db.commit(); audit(db,request,u,"attendance_marked",{"student_id":student_id,"date":attendance_date,"status":status})
    return RedirectResponse(f"/admin/attendance?date={attendance_date}",303)

@router.post("/admin/attendance/notify-inactive")
def admin_attendance_notify_inactive(request: Request, days:int=Form(3), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","support")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    days=max(1,min(days,30))
    recipient_ids=communication_recipient_ids(db,"inactive",str(days))
    title="متابعة النشاط على منصة المستشار"; body=f"لاحظنا عدم وجود نشاط على المنصة منذ {days} أيام أو أكثر. ادخل الآن لمتابعة دروسك وخطة مذاكرتك."
    campaign=CommunicationCampaign(created_by=u.id,title=title,body=body,audience_type="inactive",audience_value=str(days),channels="in_app",recipient_count=len(recipient_ids)); db.add(campaign); db.flush()
    bulk_in_app_campaign(db,campaign_id=campaign.id,recipient_ids=recipient_ids,title=title,body=body,kind="warning")
    db.commit(); audit(db,request,u,"inactive_students_notified",{"days":days,"recipients":len(recipient_ids)})
    return RedirectResponse("/admin/attendance",303)

@router.get("/schedule", response_class=HTMLResponse)
def student_schedule(request: Request, db: Session=Depends(get_db)):
    u=require_user(request,db)
    if u.role != "student": raise HTTPException(403)
    classes=student_live_classes(db,u.id)
    attendance={a.live_class_id:a for a in db.query(LiveClassAttendance).filter(LiveClassAttendance.user_id==u.id, LiveClassAttendance.live_class_id.in_([c.id for c in classes])).all()} if classes else {}
    now=datetime.utcnow(); upcoming=[c for c in classes if c.scheduled_at>=now]
    return render_template("student_schedule.html",ctx(request,db,classes=classes,attendance=attendance,next_class=(upcoming[0] if upcoming else None),now=now))

@router.post("/live-class/{class_id}/join")
def student_live_class_join(class_id:int, request:Request, csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_user(request,db)
    if u.role!="student" or not check_csrf(request.session,csrf): raise HTTPException(403)
    item=db.get(LiveClass,class_id)
    if not item or not db.query(Enrollment).filter_by(user_id=u.id,course_id=item.course_id,active=True).first(): raise HTTPException(404)
    gid=live_class_group_id(db,class_id)
    if gid and student_group_id(db,u.id)!=gid: raise HTTPException(404)
    row=db.query(LiveClassAttendance).filter_by(live_class_id=item.id,user_id=u.id).first()
    if row: row.status="present"; row.joined_at=datetime.utcnow()
    else: db.add(LiveClassAttendance(live_class_id=item.id,user_id=u.id,status="present",joined_at=datetime.utcnow()))
    db.commit(); audit(db,request,u,"live_class_joined",{"live_class_id":item.id})
    if not item.meeting_url:
        return RedirectResponse("/schedule",303)
    return RedirectResponse(safe_live_url(item.meeting_url, item.provider or "custom"),303)

@router.get("/admin/live-classes", response_class=HTMLResponse)
def admin_live_classes(request:Request, db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","content_manager")
    classes=db.query(LiveClass).order_by(LiveClass.scheduled_at.desc()).limit(100).all(); courses=db.query(Course).order_by(Course.grade,Course.title).all()
    now=datetime.utcnow(); metrics={"upcoming":sum(c.scheduled_at>=now and c.status=="scheduled" for c in classes),"today":sum(c.scheduled_at.date()==now.date() and c.status!="cancelled" for c in classes),"completed":sum(c.status=="completed" for c in classes),"total":len(classes)}
    return render_template("admin_live_classes.html",ctx(request,db,classes=classes,courses=courses,course_map={c.id:c for c in courses},metrics=metrics,now=now))

@router.post("/admin/live-classes/create")
def admin_live_class_create(request:Request, course_id:int=Form(...), title:str=Form(...), provider:str=Form("zoom"), meeting_url:str=Form(""), scheduled_at:str=Form(...), duration_minutes:int=Form(60), notes:str=Form(""), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if provider not in {"zoom","meet","teams","youtube","custom"}: raise HTTPException(400,"مزود غير صالح")
    try: dt=datetime.strptime(scheduled_at,"%Y-%m-%dT%H:%M")
    except ValueError: raise HTTPException(400,"موعد غير صالح")
    if not db.get(Course,course_id): raise HTTPException(404)
    provider = provider.strip().lower()
    safe_meeting_url = safe_live_url(meeting_url, provider)
    item=LiveClass(course_id=course_id,title=title.strip()[:180],provider=provider,meeting_url=safe_meeting_url,scheduled_at=dt,duration_minutes=max(15,min(duration_minutes,360)),notes=notes.strip()[:2000],created_by=u.id); db.add(item); db.flush()
    recipient_ids = live_class_student_ids(db, item)
    notice_title = "حصة مباشرة جديدة"
    notice_body = f"تم تحديد {item.title} يوم {dt.strftime('%Y-%m-%d')} الساعة {dt.strftime('%H:%M')}"
    campaign = CommunicationCampaign(created_by=u.id,title=notice_title,body=notice_body,audience_type="course",audience_value=str(course_id),channels="in_app",recipient_count=len(recipient_ids)); db.add(campaign); db.flush()
    bulk_in_app_campaign(db,campaign_id=campaign.id,recipient_ids=recipient_ids,title=notice_title,body=notice_body,kind="info",detail="إشعار حصة مباشرة جديدة")
    db.commit(); audit(db,request,u,"live_class_created",{"live_class_id":item.id,"course_id":course_id,"recipients":len(recipient_ids)})
    return RedirectResponse("/admin/live-classes",303)

@router.post("/admin/live-classes/{class_id}/status")
def admin_live_class_status(class_id:int, request:Request, status:str=Form(...), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if status not in {"scheduled","live","completed","cancelled"}: raise HTTPException(400)
    item=db.get(LiveClass,class_id);
    if not item: raise HTTPException(404)
    item.status=status; db.commit(); audit(db,request,u,"live_class_status_changed",{"live_class_id":class_id,"status":status})
    return RedirectResponse("/admin/live-classes",303)

@router.get("/admin/live-classes/{class_id}", response_class=HTMLResponse)
def admin_live_class_detail(class_id:int, request:Request, page:int=1, q:str="", db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","content_manager")
    item=db.get(LiveClass,class_id)
    if not item: raise HTTPException(404)
    students, page, pages, total, page_size = live_class_students(db,item,page=page,page_size=100,q=q)
    page_ids=[student.id for student in students]
    marks={x.user_id:x for x in db.query(LiveClassAttendance).filter(LiveClassAttendance.live_class_id==item.id, LiveClassAttendance.user_id.in_(page_ids or [-1])).all()}
    return render_template("admin_live_class_detail.html",ctx(request,db,item=item,students=students,marks=marks,course=db.get(Course,item.course_id),page=page,pages=pages,total=total,page_size=page_size,q=" ".join((q or "").strip().split())[:120]))

@router.post("/admin/live-classes/{class_id}/attendance")
def admin_live_class_attendance(class_id:int, request:Request, student_id:int=Form(...), status:str=Form(...), note:str=Form(""), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf) or status not in {"present","absent","excused"}: raise HTTPException(403)
    item=db.get(LiveClass,class_id)
    if not item or live_class_student_query(db,item).filter(User.id==student_id).first() is None: raise HTTPException(404)
    row=db.query(LiveClassAttendance).filter_by(live_class_id=class_id,user_id=student_id).first()
    if row: row.status=status; row.note=note.strip()[:300]; row.marked_by=u.id
    else: db.add(LiveClassAttendance(live_class_id=class_id,user_id=student_id,status=status,note=note.strip()[:300],marked_by=u.id))
    db.commit(); return RedirectResponse(f"/admin/live-classes/{class_id}",303)

@router.post("/admin/live-classes/{class_id}/notify")
def admin_live_class_notify(class_id:int, request:Request, csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    item=db.get(LiveClass,class_id)
    if not item: raise HTTPException(404)
    recipient_ids=live_class_student_ids(db,item); title="تذكير بحصة مباشرة"; body=f"موعد {item.title} يوم {item.scheduled_at.strftime('%Y-%m-%d')} الساعة {item.scheduled_at.strftime('%H:%M')}. افتح جدولك من منصة المستشار."
    campaign=CommunicationCampaign(created_by=u.id,title=title,body=body,audience_type="course",audience_value=str(item.course_id),channels="in_app",recipient_count=len(recipient_ids)); db.add(campaign); db.flush()
    bulk_in_app_campaign(db,campaign_id=campaign.id,recipient_ids=recipient_ids,title=title,body=body,kind="warning",detail="تذكير حصة مباشرة")
    db.commit(); audit(db,request,u,"live_class_reminder_sent",{"live_class_id":class_id,"recipients":len(recipient_ids)})
    return RedirectResponse(f"/admin/live-classes/{class_id}",303)

@router.get("/admin/groups", response_class=HTMLResponse)
def admin_groups(request:Request, db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","content_manager")
    groups=db.query(StudentGroup).order_by(StudentGroup.active.desc(),StudentGroup.grade,StudentGroup.name).all()
    counts={int(group_id): int(count) for group_id, count in db.query(StudentGroupMembership.group_id, func.count(StudentGroupMembership.user_id)).group_by(StudentGroupMembership.group_id).all()}
    course_counts={int(group_id): int(count) for group_id, count in db.query(GroupCourseAssignment.group_id, func.count(GroupCourseAssignment.course_id)).group_by(GroupCourseAssignment.group_id).all()}
    has_group = exists().where(StudentGroupMembership.user_id == User.id)
    ungrouped=db.query(func.count(User.id)).filter(User.role=="student",User.is_active==True,~has_group).scalar() or 0
    return render_template("admin_groups.html",ctx(request,db,groups=groups,counts=counts,course_counts=course_counts,ungrouped=int(ungrouped)))

@router.post("/admin/groups/create")
def admin_group_create(request:Request,name:str=Form(...),grade:str=Form(""),description:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    name=name.strip()[:120]
    if not name: raise HTTPException(400,"اسم المجموعة مطلوب")
    g=StudentGroup(name=name,grade=grade.strip()[:80],description=description.strip(),created_by=u.id); db.add(g); db.commit()
    audit(db,request,u,"student_group_created",{"group_id":g.id,"name":g.name})
    return RedirectResponse(f"/admin/groups/{g.id}",303)

@router.get("/admin/groups/{group_id}", response_class=HTMLResponse)
def admin_group_detail(group_id:int, request:Request, page:int=1, q:str="", student_q:str="", db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","content_manager")
    g=db.get(StudentGroup,group_id)
    if not g: raise HTTPException(404)
    q=" ".join((q or "").strip().split())[:120]; student_q=" ".join((student_q or "").strip().split())[:120]
    member_query=db.query(User).join(StudentGroupMembership,StudentGroupMembership.user_id==User.id).filter(StudentGroupMembership.group_id==g.id,User.role=="student",User.is_active==True)
    if q:
        like=f"%{q}%"; member_query=member_query.filter(or_(User.name.ilike(like),User.email.ilike(like)))
    member_total=member_query.count(); page_size=100; pages=max(1,(member_total+page_size-1)//page_size); page=min(max(1,int(page or 1)),pages)
    members=member_query.order_by(User.name,User.id).offset((page-1)*page_size).limit(page_size).all()
    has_group=exists().where(StudentGroupMembership.user_id==User.id)
    available_query=db.query(User).filter(User.role=="student",User.is_active==True,~has_group)
    if student_q:
        like=f"%{student_q}%"; available_query=available_query.filter(or_(User.name.ilike(like),User.email.ilike(like)))
    available=available_query.order_by(User.name,User.id).limit(50).all()
    assignments=db.query(GroupCourseAssignment).filter_by(group_id=g.id).all(); assigned_ids={x.course_id for x in assignments}
    courses=db.query(Course).order_by(Course.grade,Course.title).all()
    classes=db.query(LiveClass).filter(LiveClass.course_id.in_(list(assigned_ids) or [-1])).order_by(LiveClass.scheduled_at.desc()).limit(100).all()
    class_group={x.live_class_id:x.group_id for x in db.query(GroupLiveClassAssignment).filter(GroupLiveClassAssignment.live_class_id.in_([c.id for c in classes] or [-1])).all()}
    return render_template("admin_group_detail.html",ctx(request,db,group=g,members=members,member_total=member_total,page=page,pages=pages,page_size=page_size,q=q,student_q=student_q,available=available,courses=courses,assigned_ids=assigned_ids,classes=classes,class_group=class_group,course_map={c.id:c for c in courses}))

@router.post("/admin/groups/{group_id}/member")
def admin_group_member(group_id:int,request:Request,student_id:int=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    g=db.get(StudentGroup,group_id); student=db.get(User,student_id)
    if not g or not student or student.role!="student": raise HTTPException(404)
    row=db.query(StudentGroupMembership).filter_by(user_id=student_id).first()
    if row: row.group_id=group_id; row.joined_at=datetime.utcnow()
    else: db.add(StudentGroupMembership(group_id=group_id,user_id=student_id))
    for a in db.query(GroupCourseAssignment).filter_by(group_id=group_id).all(): sync_group_course(db,group_id,a.course_id)
    db.commit(); audit(db,request,u,"student_group_member_set",{"group_id":group_id,"student_id":student_id})
    return RedirectResponse(f"/admin/groups/{group_id}",303)

@router.post("/admin/groups/{group_id}/member/{student_id}/remove")
def admin_group_member_remove(group_id:int,student_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    row=db.query(StudentGroupMembership).filter_by(group_id=group_id,user_id=student_id).first()
    if row: db.delete(row); db.commit(); audit(db,request,u,"student_group_member_removed",{"group_id":group_id,"student_id":student_id})
    return RedirectResponse(f"/admin/groups/{group_id}",303)

@router.post("/admin/groups/{group_id}/course")
def admin_group_course(group_id:int,request:Request,course_id:int=Form(...),action:str=Form("assign"),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if not db.get(StudentGroup,group_id) or not db.get(Course,course_id): raise HTTPException(404)
    row=db.query(GroupCourseAssignment).filter_by(group_id=group_id,course_id=course_id).first()
    if action=="remove":
        if row: db.delete(row)
    else:
        if not row: db.add(GroupCourseAssignment(group_id=group_id,course_id=course_id))
        sync_group_course(db,group_id,course_id)
    db.commit(); audit(db,request,u,"student_group_course_changed",{"group_id":group_id,"course_id":course_id,"action":action})
    return RedirectResponse(f"/admin/groups/{group_id}",303)

@router.post("/admin/groups/{group_id}/live-class")
def admin_group_live_class(group_id:int,request:Request,live_class_id:int=Form(...),action:str=Form("assign"),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    item=db.get(LiveClass,live_class_id); g=db.get(StudentGroup,group_id)
    if not item or not g: raise HTTPException(404)
    if not db.query(GroupCourseAssignment).filter_by(group_id=group_id,course_id=item.course_id).first(): raise HTTPException(400,"الحصة يجب أن تكون من كورس مسند للمجموعة")
    row=db.query(GroupLiveClassAssignment).filter_by(live_class_id=live_class_id).first()
    if action=="remove":
        if row and row.group_id==group_id: db.delete(row)
    else:
        if row: row.group_id=group_id
        else: db.add(GroupLiveClassAssignment(group_id=group_id,live_class_id=live_class_id))
    db.commit(); audit(db,request,u,"student_group_live_class_changed",{"group_id":group_id,"live_class_id":live_class_id,"action":action})
    return RedirectResponse(f"/admin/groups/{group_id}",303)
