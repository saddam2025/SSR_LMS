from datetime import datetime, timedelta
from urllib.parse import urlparse
from fastapi import HTTPException
from sqlalchemy.orm import Session
from ..models import (User, StudentProfile, StudentAttendance, Enrollment, LiveClass, StudentGroupMembership, GroupLiveClassAssignment, GroupCourseAssignment)
from .student_activity import student_last_activity_map

SUPPORTED_LIVE_PROVIDERS = {"zoom", "meet", "teams", "youtube", "custom"}
LIVE_PROVIDER_HOSTS = {
    "zoom": {"zoom.us", "zoom.com"},
    "meet": {"meet.google.com"},
    "teams": {"teams.microsoft.com", "teams.live.com"},
    "youtube": {"youtube.com", "www.youtube.com", "youtu.be"},
}

def safe_live_url(value: str, provider: str = "custom") -> str:
    clean = value.strip()[:700]
    if not clean:
        return ""
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    provider = provider.strip().lower()
    if provider not in SUPPORTED_LIVE_PROVIDERS:
        raise HTTPException(400, "مزود الحصة غير صالح")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise HTTPException(400, "رابط الحصة يجب أن يكون HTTPS صالحًا")
    allowed = LIVE_PROVIDER_HOSTS.get(provider)
    if allowed and not any(host == h or host.endswith("." + h) for h in allowed):
        raise HTTPException(400, "رابط الحصة لا يطابق المزود المحدد")
    return clean

def student_group_id(db: Session, user_id: int):
    row=db.query(StudentGroupMembership).filter_by(user_id=user_id).first()
    return row.group_id if row else None

def group_member_ids(db: Session, group_id: int):
    return [x.user_id for x in db.query(StudentGroupMembership).filter_by(group_id=group_id).all()]

def sync_group_course(db: Session, group_id: int, course_id: int):
    for uid in group_member_ids(db,group_id):
        e=db.query(Enrollment).filter_by(user_id=uid,course_id=course_id).first()
        if e: e.active=True
        else: db.add(Enrollment(user_id=uid,course_id=course_id,active=True))

def live_class_group_id(db: Session, live_class_id: int):
    row=db.query(GroupLiveClassAssignment).filter_by(live_class_id=live_class_id).first()
    return row.group_id if row else None

def attendance_rows(db: Session, target_date: str):
    students=db.query(User).filter(User.role=="student",User.is_active==True).order_by(User.name).all()
    profiles={p.user_id:p for p in db.query(StudentProfile).all()}
    manual={a.user_id:a for a in db.query(StudentAttendance).filter(StudentAttendance.attendance_date==target_date).all()}
    last_map=student_last_activity_map(db)
    day_start=datetime.strptime(target_date,"%Y-%m-%d")
    day_end=day_start+timedelta(days=1)
    rows=[]
    for st in students:
        mark=manual.get(st.id); last=last_map.get(st.id)
        auto_present=bool(last and day_start <= last < day_end)
        status=mark.status if mark else ("present" if auto_present else "absent")
        source=mark.source if mark else ("activity" if auto_present else "auto")
        inactive_days=max(0,(datetime.utcnow().date()-last.date()).days) if last else 999
        rows.append({"student":st,"profile":profiles.get(st.id),"status":status,"source":source,"note":mark.note if mark else "","last_activity":last,"inactive_days":inactive_days})
    return rows

def student_live_classes(db: Session, user_id: int, days_before: int = 7, days_after: int = 21, course_ids: list[int] | None = None):
    now = datetime.utcnow()
    if course_ids is None:
        course_ids=[x.course_id for x in db.query(Enrollment).filter(Enrollment.user_id==user_id, Enrollment.active==True).all()]
    if not course_ids: return []
    classes=db.query(LiveClass).filter(LiveClass.course_id.in_(course_ids), LiveClass.scheduled_at >= now-timedelta(days=days_before), LiveClass.scheduled_at <= now+timedelta(days=days_after), LiveClass.status != "cancelled").order_by(LiveClass.scheduled_at).all()
    gid=student_group_id(db,user_id)
    assigned={x.live_class_id:x.group_id for x in db.query(GroupLiveClassAssignment).filter(GroupLiveClassAssignment.live_class_id.in_([c.id for c in classes] or [-1])).all()}
    return [c for c in classes if c.id not in assigned or (gid and assigned[c.id]==gid)]

def live_class_students(db: Session, live_class: LiveClass):
    ids=[x.user_id for x in db.query(Enrollment).filter(Enrollment.course_id==live_class.course_id, Enrollment.active==True).all()]
    gid=live_class_group_id(db,live_class.id)
    if gid:
        allowed=set(group_member_ids(db,gid)); ids=[x for x in ids if x in allowed]
    return db.query(User).filter(User.id.in_(ids), User.role=="student", User.is_active==True).order_by(User.name).all() if ids else []
