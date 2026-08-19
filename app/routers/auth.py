"""Authentication/account HTTP router extracted from app.main in V68."""
import os, re, secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActiveSession, OTPChallenge, StudentProfile, User
from ..permissions import STAFF_ROLES
from ..request_context import (
    IS_PRODUCTION, audit, client_ip, current_user, require_user,
    session_record, template_context as ctx,
)
from ..security import (
    REQUIRE_STAFF_MFA, check_csrf, clear_failed_logins, decrypt_secret,
    encrypt_secret, ensure_csrf, hash_password, login_allowed, new_totp_secret,
    password_needs_rehash, record_failed_login, sha256, totp_uri, verify_password,
    verify_totp,
)
from ..services.auth import create_otp, establish_session, normalize_phone

router = APIRouter()
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(APP_DIR, "templates"))


def render_template(name: str, context: dict, status_code: int = 200):
    request = context.get("request")
    if request is None:
        raise RuntimeError("Template context must include request")
    return Jinja2Templates.TemplateResponse(templates, request=request, name=name, context=context, status_code=status_code)


def _render_login(context: dict, status_code: int = 200):
    return render_template("login.html", context, status_code=status_code)


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if current_user(request, db):
        return RedirectResponse("/dashboard", 303)
    return render_template("register.html", ctx(request, db, error=None))


@router.post("/register", response_class=HTMLResponse)
def register_submit(request: Request, name: str = Form(...), email: str = Form(...), phone: str = Form(...), grade: str = Form(...), password: str = Form(...), password_confirm: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    key = f"register:{client_ip(request)}"
    if not login_allowed(key, limit=5, window=3600):
        return render_template("register.html", ctx(request, db, error="تم تجاوز عدد محاولات إنشاء الحساب. حاول لاحقًا."), status_code=429)
    full_name = " ".join(name.strip().split())[:120]
    email_norm = email.strip().lower()[:190]
    ph = normalize_phone(phone)
    valid_grades = {"الصف الأول الثانوي", "الصف الثاني الثانوي عام", "الصف الثاني بكالوريا", "الصف الثالث الثانوي"}
    if len(full_name) < 3 or "@" not in email_norm or len(ph) < 11 or grade not in valid_grades:
        record_failed_login(key, window=3600)
        return render_template("register.html", ctx(request, db, error="راجع الاسم والبريد ورقم الهاتف والصف الدراسي."), status_code=400)
    if password != password_confirm or len(password) < 12 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return render_template("register.html", ctx(request, db, error="كلمة المرور يجب ألا تقل عن 12 حرفًا وتحتوي حروفًا وأرقامًا، ويجب أن يتطابق التأكيد."), status_code=400)
    if db.query(User).filter(func.lower(User.email) == email_norm).first() or db.query(StudentProfile).filter(StudentProfile.phone == ph).first():
        return render_template("register.html", ctx(request, db, error="تعذر إنشاء الحساب بهذه البيانات."), status_code=409)
    u = User(name=full_name, email=email_norm, password_hash=hash_password(password), role="student", is_active=True)
    db.add(u); db.flush()
    db.add(StudentProfile(user_id=u.id, phone=ph, grade=grade))
    db.commit(); clear_failed_logins(key); audit(db, request, u, "student_registered")
    return establish_session(request, db, u, _render_login)


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(request: Request, db: Session = Depends(get_db)):
    return render_template("forgot_password.html", ctx(request, db, error=None, step="request", dev_code=None))


@router.post("/forgot-password/request", response_class=HTMLResponse)
def forgot_password_request(request: Request, phone: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    key = f"reset:{client_ip(request)}"
    if not login_allowed(key, limit=5, window=3600):
        return render_template("forgot_password.html", ctx(request, db, error="تم تجاوز عدد المحاولات. حاول لاحقًا.", step="request", dev_code=None), status_code=429)
    ph = normalize_phone(phone)
    profile = db.query(StudentProfile).filter_by(phone=ph).first() if ph else None
    dev_code = None
    if profile:
        u = db.get(User, profile.user_id)
        if u and u.is_active:
            try:
                dev_code = create_otp(db, u, ph, "password_reset")
                request.session["reset_uid"] = u.id; request.session["reset_phone"] = ph
            except HTTPException:
                if IS_PRODUCTION: raise
    return render_template("forgot_password.html", ctx(request, db, error=None, step="verify", dev_code=(dev_code if not IS_PRODUCTION else None)))


@router.post("/forgot-password/verify", response_class=HTMLResponse)
def forgot_password_verify(request: Request, code: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    uid=request.session.get("reset_uid"); ph=request.session.get("reset_phone"); now=datetime.utcnow()
    ch=(db.query(OTPChallenge).filter(OTPChallenge.user_id==uid,OTPChallenge.phone==ph,OTPChallenge.purpose=="password_reset",OTPChallenge.used_at.is_(None)).order_by(OTPChallenge.id.desc()).first() if uid else None)
    if not ch or ch.expires_at < now or ch.attempts >= 5:
        return render_template("forgot_password.html", ctx(request, db, error="انتهت صلاحية الرمز. اطلب رمزًا جديدًا.", step="request", dev_code=None), status_code=401)
    ch.attempts += 1
    if not secrets.compare_digest(ch.code_hash, sha256(code.strip())):
        db.commit(); return render_template("forgot_password.html", ctx(request, db, error="رمز التحقق غير صحيح.", step="verify", dev_code=None), status_code=401)
    ch.used_at=now; db.commit(); request.session["reset_verified_uid"] = uid
    request.session.pop("reset_uid", None); request.session.pop("reset_phone", None)
    return render_template("forgot_password.html", ctx(request, db, error=None, step="new_password", dev_code=None))


@router.post("/forgot-password/complete", response_class=HTMLResponse)
def forgot_password_complete(request: Request, password: str = Form(...), password_confirm: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    uid = request.session.get("reset_verified_uid")
    if not uid: raise HTTPException(403)
    if password != password_confirm or len(password) < 12 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return render_template("forgot_password.html", ctx(request, db, error="كلمة المرور يجب ألا تقل عن 12 حرفًا وتحتوي حروفًا وأرقامًا، ويجب أن يتطابق التأكيد.", step="new_password", dev_code=None), status_code=400)
    u = db.get(User, int(uid))
    if not u or not u.is_active: raise HTTPException(403)
    u.password_hash = hash_password(password); now = datetime.utcnow()
    db.query(ActiveSession).filter(ActiveSession.user_id == u.id, ActiveSession.revoked_at.is_(None)).update({ActiveSession.revoked_at: now}, synchronize_session=False)
    db.commit(); audit(db, request, u, "password_reset_completed"); request.session.clear()
    return RedirectResponse("/login?reset=1", 303)


@router.get("/Login", response_class=HTMLResponse, include_in_schema=False)
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    return render_template("login.html", ctx(request, db, error=None))


@router.post("/Login", include_in_schema=False)
@router.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403, "CSRF failed")
    email_norm = email.strip().lower(); phone_norm = normalize_phone(email)
    key = f"{client_ip(request)}:{sha256(email_norm)[:20]}"
    if not login_allowed(key):
        audit(db, request, None, "login_rate_limited", {"email_hash": sha256(email_norm)[:16]})
        return render_template("login.html", ctx(request, db, error="تم إيقاف المحاولات مؤقتًا. حاول لاحقًا."), status_code=429)
    u = db.query(User).filter(func.lower(User.email) == email_norm).first()
    if not u and phone_norm:
        profile = db.query(StudentProfile).filter(StudentProfile.phone == phone_norm).first(); u = db.get(User, profile.user_id) if profile else None
    now = datetime.utcnow()
    if u and u.locked_until and u.locked_until > now:
        audit(db, request, u, "account_locked_login_attempt")
        return render_template("login.html", ctx(request, db, error="الحساب مقفل مؤقتًا بسبب محاولات دخول متكررة."), status_code=423)
    if not u or not verify_password(password, u.password_hash):
        record_failed_login(key)
        if u:
            u.failed_login_count += 1
            if u.failed_login_count >= 8:
                u.locked_until = now + timedelta(minutes=15); u.failed_login_count = 0
            db.commit()
        audit(db, request, u, "login_failed", {"email_hash": sha256(email_norm)[:16]})
        return render_template("login.html", ctx(request, db, error="بيانات الدخول غير صحيحة."), status_code=401)
    clear_failed_logins(key); u.failed_login_count = 0; u.locked_until = None
    if password_needs_rehash(u.password_hash): u.password_hash = hash_password(password)
    if REQUIRE_STAFF_MFA and u.mfa_enabled:
        request.session.clear(); request.session["preauth_uid"] = u.id; request.session["preauth_exp"] = int(datetime.utcnow().timestamp()) + 300
        ensure_csrf(request.session); db.commit(); return RedirectResponse("/mfa", 303)
    return establish_session(request, db, u, _render_login)


@router.get("/mfa", response_class=HTMLResponse)
def mfa_page(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("preauth_uid"); exp = int(request.session.get("preauth_exp") or 0)
    u = db.get(User, uid) if uid and exp >= int(datetime.utcnow().timestamp()) else None
    if not u or not u.mfa_enabled:
        request.session.clear(); return RedirectResponse("/login", 303)
    return render_template("mfa.html", {"request": request, "csrf": ensure_csrf(request.session), "error": None})


@router.post("/mfa")
def mfa_verify(request: Request, code: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    uid = request.session.get("preauth_uid"); exp = int(request.session.get("preauth_exp") or 0)
    u = db.get(User, uid) if uid and exp >= int(datetime.utcnow().timestamp()) else None
    if not u or not u.mfa_enabled:
        request.session.clear(); return RedirectResponse("/login", 303)
    key = f"mfa:{client_ip(request)}:{u.id}"
    if not login_allowed(key, limit=6, window=600):
        return render_template("mfa.html", {"request": request, "csrf": ensure_csrf(request.session), "error": "تم إيقاف محاولات الرمز مؤقتًا."}, status_code=429)
    if not verify_totp(decrypt_secret(u.mfa_secret or ""), code):
        record_failed_login(key); audit(db, request, u, "mfa_failed")
        return render_template("mfa.html", {"request": request, "csrf": ensure_csrf(request.session), "error": "رمز التحقق غير صحيح."}, status_code=401)
    clear_failed_logins(key); request.session.clear(); audit(db, request, u, "mfa_verified")
    return establish_session(request, db, u, _render_login)


@router.get("/account/security", response_class=HTMLResponse)
def account_security(request: Request, db: Session = Depends(get_db)):
    u = require_user(request, db); pending = request.session.get("mfa_pending_secret")
    if not pending and not u.mfa_enabled:
        pending = new_totp_secret(); request.session["mfa_pending_secret"] = pending
    uri = totp_uri(pending, u.email) if pending and not u.mfa_enabled else ""
    return render_template("account_security.html", ctx(request, db, pending_secret=pending, otpauth_uri=uri, mfa_required=bool(REQUIRE_STAFF_MFA and u.role in STAFF_ROLES), error=None))


@router.post("/account/security/mfa/enable")
def account_mfa_enable(request: Request, code: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_user(request, db)
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    secret = request.session.get("mfa_pending_secret")
    if not secret or not verify_totp(secret, code):
        uri = totp_uri(secret, u.email) if secret else ""
        return render_template("account_security.html", ctx(request, db, pending_secret=secret, otpauth_uri=uri, mfa_required=bool(REQUIRE_STAFF_MFA and u.role in STAFF_ROLES), error="الرمز غير صحيح. تأكد من ضبط الوقت في تطبيق المصادقة."), status_code=400)
    u.mfa_secret = encrypt_secret(secret); u.mfa_enabled = True; db.commit(); request.session.pop("mfa_pending_secret", None)
    audit(db, request, u, "mfa_enabled"); return RedirectResponse("/account/security", 303)


@router.post("/account/password")
def account_change_password(request: Request, current_password: str = Form(...), new_password: str = Form(...), csrf: str = Form(...), db: Session = Depends(get_db)):
    u = require_user(request, db)
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    if not verify_password(current_password, u.password_hash): raise HTTPException(403, "كلمة المرور الحالية غير صحيحة")
    if len(new_password) < 12 or not re.search(r"[A-Za-z]", new_password) or not re.search(r"\d", new_password):
        raise HTTPException(400, "استخدم كلمة مرور لا تقل عن 12 حرفًا وتحتوي حروفًا وأرقامًا")
    u.password_hash = hash_password(new_password); now = datetime.utcnow(); current = session_record(request, db)
    q = db.query(ActiveSession).filter(ActiveSession.user_id == u.id, ActiveSession.revoked_at.is_(None))
    if current: q = q.filter(ActiveSession.id != current.id)
    q.update({ActiveSession.revoked_at: now}, synchronize_session=False)
    db.commit(); audit(db, request, u, "password_changed"); return RedirectResponse("/account/security", 303)


@router.post("/logout")
def logout(request: Request, csrf: str = Form(...), db: Session = Depends(get_db)):
    if not check_csrf(request.session, csrf): raise HTTPException(403)
    u = current_user(request, db); rec = session_record(request, db)
    if rec and not rec.revoked_at:
        rec.revoked_at = datetime.utcnow(); db.commit()
    if u: audit(db, request, u, "logout")
    request.session.clear(); return RedirectResponse("/", 303)


@router.get("/otp-login", response_class=HTMLResponse)
def otp_login_page(request: Request, db: Session = Depends(get_db)):
    return render_template("otp_login.html",ctx(request,db,error=None,dev_code=None,step="request"))


@router.post("/otp-login/request", response_class=HTMLResponse)
def otp_login_request(request:Request,phone:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    ph=normalize_phone(phone); profile=db.query(StudentProfile).filter_by(phone=ph).first() if ph else None
    dev_code=None
    if profile:
        u=db.get(User,profile.user_id)
        if u and u.is_active:
            dev_code=create_otp(db,u,ph,"login"); request.session["otp_uid"]=u.id; request.session["otp_phone"]=ph
    return render_template("otp_login.html",ctx(request,db,error=None,dev_code=(dev_code if not IS_PRODUCTION else None),step="verify"))


@router.post("/otp-login/verify", response_class=HTMLResponse)
def otp_login_verify(request:Request,code:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    uid=request.session.get("otp_uid"); ph=request.session.get("otp_phone"); now=datetime.utcnow()
    ch=(db.query(OTPChallenge).filter(OTPChallenge.user_id==uid,OTPChallenge.phone==ph,OTPChallenge.purpose=="login",OTPChallenge.used_at.is_(None)).order_by(OTPChallenge.id.desc()).first() if uid else None)
    if not ch or ch.expires_at<now or ch.attempts>=5:
        return render_template("otp_login.html",ctx(request,db,error="انتهت صلاحية الرمز. اطلب رمزًا جديدًا.",dev_code=None,step="request"),status_code=401)
    ch.attempts+=1
    if not secrets.compare_digest(ch.code_hash,sha256(code.strip())):
        db.commit(); return render_template("otp_login.html",ctx(request,db,error="رمز التحقق غير صحيح.",dev_code=None,step="verify"),status_code=401)
    ch.used_at=now; u=db.get(User,uid); db.commit(); request.session.pop("otp_uid",None); request.session.pop("otp_phone",None)
    audit(db,request,u,"otp_login_success"); return establish_session(request,db,u,_render_login)
