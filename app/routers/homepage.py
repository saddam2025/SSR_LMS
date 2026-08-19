from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Course, HomepageFeature, HomepageReel, HomepageHonor, HomepageReview
from ..permissions import ROLE_LABELS
from ..request_context import IS_PRODUCTION, audit, current_user, require_role, template_context as ctx
from ..security import check_csrf
from ..services.homepage import feature_enabled, safe_reel_url
from ..services.template_rendering import render_template

router = APIRouter()

@router.get("/Home", response_class=HTMLResponse, include_in_schema=False)
@router.get("/home", response_class=HTMLResponse, include_in_schema=False)
@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    courses = db.query(Course).filter(Course.published == True).order_by(Course.id.desc()).all()
    reels_enabled = feature_enabled(db, "reels", True)
    honors_enabled = feature_enabled(db, "honors", True)
    reviews_enabled = feature_enabled(db, "reviews", True)
    reels = db.query(HomepageReel).filter(HomepageReel.active == True).order_by(HomepageReel.sort_order.asc(), HomepageReel.id.desc()).limit(6).all() if reels_enabled else []
    honors = db.query(HomepageHonor).filter(HomepageHonor.active == True).order_by(HomepageHonor.sort_order.asc(), HomepageHonor.id.asc()).limit(12).all() if honors_enabled else []
    reviews = db.query(HomepageReview).filter(HomepageReview.active == True).order_by(HomepageReview.sort_order.asc(), HomepageReview.id.asc()).limit(12).all() if reviews_enabled else []
    u = current_user(request, db)
    if u:
        context = ctx(request, db, courses=courses, reels=reels, honors=honors, reviews=reviews, reels_enabled=reels_enabled, honors_enabled=honors_enabled, reviews_enabled=reviews_enabled)
    else:
        context = {
            "request": request, "user": None, "csrf": "", "unread_notifications": 0,
            "staff_mfa_pending": False, "role_labels": ROLE_LABELS, "is_production": IS_PRODUCTION,
            "courses": courses, "reels": reels, "honors": honors, "reviews": reviews,
            "reels_enabled": reels_enabled, "honors_enabled": honors_enabled, "reviews_enabled": reviews_enabled,
        }
    return render_template("home.html", context)

@router.get("/Courses", include_in_schema=False)
@router.get("/courses", include_in_schema=False)
def courses_alias():
    return RedirectResponse("/#courses", 303)

@router.get("/admin/homepage", response_class=HTMLResponse)
def admin_homepage(request: Request, db: Session = Depends(get_db)):
    require_role(request, db, "admin")
    reels = db.query(HomepageReel).order_by(HomepageReel.sort_order.asc(), HomepageReel.id.desc()).all()
    honors = db.query(HomepageHonor).order_by(HomepageHonor.sort_order.asc(), HomepageHonor.id.asc()).all()
    reviews = db.query(HomepageReview).order_by(HomepageReview.sort_order.asc(), HomepageReview.id.asc()).all()
    return render_template("admin_homepage.html", ctx(request, db, reels=reels, honors=honors, reviews=reviews,
        reels_enabled=feature_enabled(db, "reels", True), honors_enabled=feature_enabled(db, "honors", True), reviews_enabled=feature_enabled(db, "reviews", True)))

@router.post("/admin/homepage/features")
def admin_homepage_features(request: Request, reels_enabled: str = Form(""), honors_enabled: str = Form(""), reviews_enabled: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    for key, enabled in (("reels", bool(reels_enabled)), ("honors", bool(honors_enabled)), ("reviews", bool(reviews_enabled))):
        row = db.query(HomepageFeature).filter_by(key=key).first()
        if not row:
            row = HomepageFeature(key=key, enabled=enabled); db.add(row)
        else: row.enabled = enabled
    db.commit(); audit(db, request, u, "homepage_features_updated", {"reels": bool(reels_enabled), "honors": bool(honors_enabled), "reviews": bool(reviews_enabled)})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/reels")
def admin_homepage_reel_create(request: Request, title: str = Form(...), url: str = Form(...), caption: str = Form(""), sort_order: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    clean_title = " ".join(title.strip().split())[:180]
    if len(clean_title) < 2: raise HTTPException(400, "عنوان الريل قصير")
    reel = HomepageReel(title=clean_title, url=safe_reel_url(url), caption=" ".join(caption.strip().split())[:300], sort_order=max(-999, min(sort_order, 999)), active=True)
    db.add(reel); db.commit(); audit(db, request, u, "homepage_reel_created", {"reel_id": reel.id})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/reels/{reel_id}/toggle")
def admin_homepage_reel_toggle(reel_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    reel = db.get(HomepageReel, reel_id)
    if not reel: raise HTTPException(404)
    reel.active = not reel.active; db.commit(); audit(db, request, u, "homepage_reel_toggled", {"reel_id": reel.id, "active": reel.active})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/reels/{reel_id}/delete")
def admin_homepage_reel_delete(reel_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    reel = db.get(HomepageReel, reel_id)
    if not reel: raise HTTPException(404)
    db.delete(reel); db.commit(); audit(db, request, u, "homepage_reel_deleted", {"reel_id": reel_id})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/honors")
def admin_homepage_honor_create(request: Request, student_name: str = Form(...), grade: str = Form(""), rank_label: str = Form(""), score_text: str = Form(""), note: str = Form(""), sort_order: int = Form(0), consent_confirmed: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    clean_name = " ".join(student_name.strip().split())[:140]
    if len(clean_name) < 2: raise HTTPException(400, "اسم الطالب قصير")
    if consent_confirmed not in {"1", "true", "yes", "on"}: raise HTTPException(400, "يجب تأكيد وجود موافقة على نشر اسم الطالب في الواجهة العامة")
    honor = HomepageHonor(student_name=clean_name, grade=" ".join(grade.strip().split())[:100], rank_label=" ".join(rank_label.strip().split())[:80], score_text=" ".join(score_text.strip().split())[:80], note=" ".join(note.strip().split())[:250], sort_order=max(-999, min(sort_order, 999)), active=True)
    db.add(honor); db.commit(); audit(db, request, u, "homepage_honor_created", {"honor_id": honor.id})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/honors/{honor_id}/toggle")
def admin_homepage_honor_toggle(honor_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    honor = db.get(HomepageHonor, honor_id)
    if not honor: raise HTTPException(404)
    honor.active = not honor.active; db.commit(); audit(db, request, u, "homepage_honor_toggled", {"honor_id": honor.id, "active": honor.active})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/honors/{honor_id}/delete")
def admin_homepage_honor_delete(honor_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    honor = db.get(HomepageHonor, honor_id)
    if not honor: raise HTTPException(404)
    db.delete(honor); db.commit(); audit(db, request, u, "homepage_honor_deleted", {"honor_id": honor_id})
    return RedirectResponse("/admin/homepage", 303)


@router.post("/admin/homepage/reviews")
def admin_homepage_review_create(request: Request, student_name: str = Form(...), grade: str = Form(""), review_text: str = Form(...), rating: int = Form(5), sort_order: int = Form(0), consent_confirmed: str = Form(""), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    clean_name = " ".join(student_name.strip().split())[:140]
    clean_grade = " ".join(grade.strip().split())[:100]
    clean_review = " ".join(review_text.strip().split())[:700]
    if len(clean_name) < 2: raise HTTPException(400, "اسم الطالب قصير")
    if len(clean_review) < 8: raise HTTPException(400, "نص الرأي قصير")
    if consent_confirmed not in {"1", "true", "yes", "on"}: raise HTTPException(400, "يجب تأكيد وجود موافقة مناسبة على نشر رأي الطالب")
    review = HomepageReview(student_name=clean_name, grade=clean_grade, review_text=clean_review, rating=max(1, min(int(rating), 5)), sort_order=max(-999, min(sort_order, 999)), active=True)
    db.add(review); db.commit(); audit(db, request, u, "homepage_review_created", {"review_id": review.id})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/reviews/{review_id}/edit")
def admin_homepage_review_edit(review_id: int, request: Request, student_name: str = Form(...), grade: str = Form(""), review_text: str = Form(...), rating: int = Form(5), sort_order: int = Form(0), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    review = db.get(HomepageReview, review_id)
    if not review: raise HTTPException(404)
    clean_name = " ".join(student_name.strip().split())[:140]
    clean_grade = " ".join(grade.strip().split())[:100]
    clean_review = " ".join(review_text.strip().split())[:700]
    if len(clean_name) < 2: raise HTTPException(400, "اسم الطالب قصير")
    if len(clean_review) < 8: raise HTTPException(400, "نص الرأي قصير")
    review.student_name = clean_name
    review.grade = clean_grade
    review.review_text = clean_review
    review.rating = max(1, min(int(rating), 5))
    review.sort_order = max(-999, min(sort_order, 999))
    db.commit(); audit(db, request, u, "homepage_review_updated", {"review_id": review.id})
    return RedirectResponse("/admin/homepage", 303)


@router.post("/admin/homepage/reviews/{review_id}/toggle")
def admin_homepage_review_toggle(review_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    review = db.get(HomepageReview, review_id)
    if not review: raise HTTPException(404)
    review.active = not review.active; db.commit(); audit(db, request, u, "homepage_review_toggled", {"review_id": review.id, "active": review.active})
    return RedirectResponse("/admin/homepage", 303)

@router.post("/admin/homepage/reviews/{review_id}/delete")
def admin_homepage_review_delete(review_id: int, request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_role(request, db, "admin")
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    review = db.get(HomepageReview, review_id)
    if not review: raise HTTPException(404)
    db.delete(review); db.commit(); audit(db, request, u, "homepage_review_deleted", {"review_id": review_id})
    return RedirectResponse("/admin/homepage", 303)
