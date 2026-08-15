import re, secrets
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import Course, CourseCategory, CourseCategoryAssignment
from ..request_context import require_role, template_context as ctx, audit
from ..security import check_csrf
from ..services.template_rendering import render_template
router=APIRouter()

def category_slug(value: str) -> str:
 raw="-".join(value.strip().lower().split()); slug=re.sub(r"[^a-z0-9\u0600-\u06ff-]+","",raw); slug=re.sub(r"-+","-",slug).strip("-"); return slug[:140] or f"category-{secrets.token_hex(4)}"

@router.get("/admin/courses", response_class=HTMLResponse)
def admin_courses_page(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "content_manager")
    courses = db.query(Course).order_by(Course.id.desc()).all()
    categories = db.query(CourseCategory).order_by(CourseCategory.sort_order, CourseCategory.name).all()
    assignments = db.query(CourseCategoryAssignment).all()
    category_by_course = {a.course_id: db.get(CourseCategory, a.category_id) for a in assignments}
    return render_template("admin_courses.html", ctx(request, db, courses=courses, categories=categories, category_by_course=category_by_course))

@router.get("/admin/courses/categories", response_class=HTMLResponse)
@router.get("/dashboard/courses/categories", response_class=HTMLResponse)
def admin_course_categories(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "super_admin", "admin", "content_manager")
    categories = db.query(CourseCategory).order_by(CourseCategory.sort_order, CourseCategory.id.desc()).all()
    counts = dict(db.query(CourseCategoryAssignment.category_id, func.count(CourseCategoryAssignment.id)).group_by(CourseCategoryAssignment.category_id).all())
    return render_template("admin_categories.html", ctx(request, db, categories=categories, category_counts=counts))

@router.get("/admin/courses/categories/add", response_class=HTMLResponse)
@router.get("/dashboard/courses/categories/add", response_class=HTMLResponse)
def admin_course_category_add_page(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    return render_template("admin_category_add.html", ctx(request, db, error=None))

@router.post("/admin/courses/categories")
@router.post("/dashboard/courses/categories")
def admin_course_category_create(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    grade: str = Form(""),
    sort_order: int = Form(0),
    csrf: str = Form(...),
    db: Session = Depends(get_db),
):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    clean_name = " ".join(name.strip().split())[:120]
    if len(clean_name) < 2: raise HTTPException(400, "اسم التصنيف قصير")
    valid_grades = {"", "الصف الأول الثانوي", "الصف الثاني الثانوي عام", "الصف الثاني بكالوريا", "الصف الثالث الثانوي"}
    if grade not in valid_grades: raise HTTPException(400, "الصف الدراسي غير صالح")
    if db.query(CourseCategory).filter(func.lower(CourseCategory.name) == clean_name.lower()).first():
        raise HTTPException(409, "التصنيف موجود بالفعل")
    base_slug = category_slug(clean_name)
    slug = base_slug
    n = 2
    while db.query(CourseCategory).filter(CourseCategory.slug == slug).first():
        slug = f"{base_slug}-{n}"[:140]; n += 1
    category = CourseCategory(name=clean_name, slug=slug, description=description.strip()[:1000], grade=grade, sort_order=max(-999, min(999, sort_order)), active=True)
    db.add(category); db.commit(); audit(db, request, admin, "course_category_created", {"category_id": category.id})
    return RedirectResponse("/admin/courses/categories", 303)

@router.post("/admin/courses/categories/{category_id}/toggle")
def admin_course_category_toggle(category_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    category = db.get(CourseCategory, category_id)
    if not category: raise HTTPException(404)
    category.active = not category.active
    db.commit(); audit(db, request, admin, "course_category_toggled", {"category_id": category.id, "active": category.active})
    return RedirectResponse("/admin/courses/categories", 303)

@router.post("/admin/courses/categories/{category_id}/delete")
def admin_course_category_delete(category_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    category = db.get(CourseCategory, category_id)
    if not category: raise HTTPException(404)
    db.query(CourseCategoryAssignment).filter(CourseCategoryAssignment.category_id == category_id).delete(synchronize_session=False)
    db.delete(category); db.commit(); audit(db, request, admin, "course_category_deleted", {"category_id": category_id})
    return RedirectResponse("/admin/courses/categories", 303)

@router.post("/admin/course/{course_id}/category")
def admin_course_category_assign(course_id: int, request: Request, category_id: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    admin = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    course = db.get(Course, course_id)
    if not course: raise HTTPException(404)
    current = db.query(CourseCategoryAssignment).filter(CourseCategoryAssignment.course_id == course_id).first()
    if category_id <= 0:
        if current: db.delete(current)
    else:
        category = db.get(CourseCategory, category_id)
        if not category: raise HTTPException(404)
        if current: current.category_id = category_id
        else: db.add(CourseCategoryAssignment(course_id=course_id, category_id=category_id))
    db.commit(); audit(db, request, admin, "course_category_assigned", {"course_id": course_id, "category_id": category_id})
    return RedirectResponse("/admin/courses", 303)

