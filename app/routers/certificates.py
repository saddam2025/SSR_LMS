import io, os, re
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import User, Course, CourseCompletionPolicy, CourseCertificate
from ..permissions import can_manage_course
from ..request_context import require_user, require_role, template_context as ctx, audit
from ..security import check_csrf
from ..services.template_rendering import render_template
router=APIRouter()
PUBLIC_BASE_URL=os.getenv("PUBLIC_BASE_URL","").rstrip("/")

@router.post("/admin/course/{course_id}/completion-policy")
def update_completion_policy(course_id:int, request:Request, require_all_lessons:str=Form(""), require_quizzes:str=Form(""), minimum_quiz_average:int=Form(60), require_homeworks:str=Form(""), minimum_homework_average:int=Form(60), certificate_enabled:str=Form(""), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","content_manager")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    c=db.get(Course,course_id)
    if not c or not can_manage_course(u.role,teacher_id=c.teacher_id,user_id=u.id): raise HTTPException(403)
    p=db.query(CourseCompletionPolicy).filter_by(course_id=course_id).first()
    if not p: p=CourseCompletionPolicy(course_id=course_id); db.add(p)
    p.require_all_lessons=require_all_lessons.lower() in {"1","true","on","yes"}
    p.require_quizzes=require_quizzes.lower() in {"1","true","on","yes"}; p.minimum_quiz_average=max(0,min(100,int(minimum_quiz_average)))
    p.require_homeworks=require_homeworks.lower() in {"1","true","on","yes"}; p.minimum_homework_average=max(0,min(100,int(minimum_homework_average)))
    p.certificate_enabled=certificate_enabled.lower() in {"1","true","on","yes"}
    db.commit(); audit(db,request,u,"completion_policy_updated",{"course_id":course_id})
    return RedirectResponse(f"/admin/course/{course_id}#completion-policy",303)

@router.get("/certificate/{certificate_id}", response_class=HTMLResponse)
def certificate_page(certificate_id:int, request:Request, db:Session=Depends(get_db)):
    u=require_user(request,db); cert=db.get(CourseCertificate,certificate_id)
    if not cert or cert.revoked_at or (u.id != cert.user_id and u.role not in {"super_admin","admin","content_manager"}): raise HTTPException(404)
    student=db.get(User,cert.user_id); course=db.get(Course,cert.course_id)
    verify_url=f"{PUBLIC_BASE_URL or str(request.base_url).rstrip('/')}/certificate/verify/{cert.verification_code}"
    return render_template("certificate.html",ctx(request,db,certificate=cert,student=student,course=course,verify_url=verify_url))

@router.get("/certificate/verify/{code}", response_class=HTMLResponse)
def certificate_verify(code:str, request:Request, db:Session=Depends(get_db)):
    cert=db.query(CourseCertificate).filter_by(verification_code=code).first()
    student=db.get(User,cert.user_id) if cert else None; course=db.get(Course,cert.course_id) if cert else None
    return render_template("certificate_verify.html",ctx(request,db,certificate=cert,student=student,course=course,valid=bool(cert and not cert.revoked_at)))

@router.get("/certificate/{certificate_id}/qr.png")
def certificate_qr(certificate_id:int, request:Request, db:Session=Depends(get_db)):
    cert=db.get(CourseCertificate,certificate_id)
    if not cert or cert.revoked_at: raise HTTPException(404)
    import qrcode
    url=f"{PUBLIC_BASE_URL or str(request.base_url).rstrip('/')}/certificate/verify/{cert.verification_code}"
    img=qrcode.make(url); buf=io.BytesIO(); img.save(buf,format="PNG")
    return Response(buf.getvalue(),media_type="image/png",headers={"Cache-Control":"public, max-age=3600"})

@router.get("/certificate/{certificate_id}/download.pdf")
def certificate_pdf(certificate_id:int, request:Request, db:Session=Depends(get_db)):
    u=require_user(request,db); cert=db.get(CourseCertificate,certificate_id)
    if not cert or cert.revoked_at or (u.id != cert.user_id and u.role not in {"super_admin","admin","content_manager"}): raise HTTPException(404)
    student=db.get(User,cert.user_id); course=db.get(Course,cert.course_id)
    import qrcode
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib.utils import ImageReader
    buf=io.BytesIO(); size=landscape(A4); cv=canvas.Canvas(buf,pagesize=size); w,h=size
    font_path="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    try: pdfmetrics.registerFont(TTFont("CertFont",font_path)); font="CertFont"
    except Exception: font="Helvetica"
    cv.setLineWidth(3); cv.rect(24,24,w-48,h-48)
    cv.setFont(font,30); cv.drawCentredString(w/2,h-90,"Al-Mostashar Certificate")
    cv.setFont(font,16); cv.drawCentredString(w/2,h-135,"This certifies successful completion")
    from PIL import Image, ImageDraw, ImageFont
    def _draw_centered_unicode(text_value, y, px_size, max_width=620):
        try:
            pil_font=ImageFont.truetype(font_path, px_size)
            probe=Image.new("RGBA", (max_width, 90), (255,255,255,0)); draw=ImageDraw.Draw(probe)
            direction="rtl" if re.search(r"[\u0600-\u06FF]", text_value or "") else "ltr"
            bbox=draw.textbbox((0,0), text_value or "", font=pil_font, direction=direction)
            tw=max(1,bbox[2]-bbox[0]); th=max(1,bbox[3]-bbox[1]); img=Image.new("RGBA", (min(max_width,tw+24), th+22), (255,255,255,0)); d=ImageDraw.Draw(img)
            d.text((img.width/2, 8), text_value or "", font=pil_font, fill=(0,0,0,255), anchor="ma", direction=direction)
            ib=io.BytesIO(); img.save(ib,format="PNG"); ib.seek(0); ratio=img.width/max(1,img.height); dh=42 if px_size>=30 else 34; dw=min(max_width,dh*ratio)
            cv.drawImage(ImageReader(ib),w/2-dw/2,y-dh/2,dw,dh,mask='auto')
        except Exception:
            cv.setFont(font,max(12,px_size*0.55)); cv.drawCentredString(w/2,y,text_value or "")
    _draw_centered_unicode(student.name,h-185,38)
    _draw_centered_unicode(course.title,h-230,30)
    cv.setFont(font,13); cv.drawCentredString(w/2,h-270,f"Final score: {cert.final_score:.1f}%   |   Issued: {cert.issued_at.strftime('%Y-%m-%d')}")
    verify_url=f"{PUBLIC_BASE_URL or str(request.base_url).rstrip('/')}/certificate/verify/{cert.verification_code}"
    img=qrcode.make(verify_url); qbuf=io.BytesIO(); img.save(qbuf,format="PNG"); qbuf.seek(0)
    cv.drawImage(ImageReader(qbuf),w/2-55,65,110,110,mask='auto')
    cv.setFont(font,9); cv.drawCentredString(w/2,48,f"Verification: {cert.verification_code}")
    cv.save(); buf.seek(0)
    return StreamingResponse(buf,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="certificate-{cert.id}.pdf"'})

@router.post("/admin/certificate/{certificate_id}/revoke")
def certificate_revoke(certificate_id:int, request:Request, reason:str=Form(""), csrf:str=Form(...), db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    cert=db.get(CourseCertificate,certificate_id)
    if not cert: raise HTTPException(404)
    cert.revoked_at=datetime.utcnow(); cert.revoked_reason=reason.strip()[:300]; db.commit(); audit(db,request,u,"certificate_revoked",{"certificate_id":cert.id})
    return RedirectResponse(f"/admin/student/{cert.user_id}",303)

