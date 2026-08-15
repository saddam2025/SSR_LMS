import html, io, secrets
from datetime import datetime
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ActivationCode, ActivationCodeBatch, ActivationCodeInventory, ActivationRedemption, Course, User
from ..request_context import require_role, audit, template_context as ctx
from ..security import check_csrf
from ..services.activation_codes import batch_rows as _activation_batch_rows, redeem_code
from ..services.learning_runtime import award_points
from ..services.template_rendering import render_template

router = APIRouter()
@router.get("/admin/code-inventory", response_class=HTMLResponse)
def admin_code_inventory(request:Request, db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","accounting")
    now=datetime.utcnow(); batches=db.query(ActivationCodeBatch).order_by(ActivationCodeBatch.id.desc()).all(); courses=db.query(Course).order_by(Course.title).all()
    stats=[]
    for b in batches:
        rows=_activation_batch_rows(db,b.id); codes=[c for _,c in rows if c]
        used=sum(1 for c in codes if c.used_count>=c.max_uses); expired=sum(1 for c in codes if c.expires_at and c.expires_at<=now and c.used_count<c.max_uses); available=sum(1 for c in codes if c.active and c.used_count<c.max_uses and (not c.expires_at or c.expires_at>now))
        stats.append({"batch":b,"course":db.get(Course,b.course_id),"total":len(codes),"used":used,"expired":expired,"available":available})
    totals={"batches":len(batches),"codes":sum(x["total"] for x in stats),"available":sum(x["available"] for x in stats),"used":sum(x["used"] for x in stats),"expired":sum(x["expired"] for x in stats)}
    return render_template("admin_code_inventory.html",ctx(request,db,batch_stats=stats,courses=courses,totals=totals))

@router.post("/admin/code-inventory/batches")
def admin_code_batch_create(request:Request,course_id:int=Form(...),name:str=Form(...),quantity:int=Form(...),distributor:str=Form(""),expires_at:str=Form(""),notes:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","accounting")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if not db.get(Course,course_id): raise HTTPException(404)
    qty=max(1,min(int(quantity),5000)); expiry=None
    if expires_at.strip():
        try: expiry=datetime.fromisoformat(expires_at.strip())
        except ValueError: raise HTTPException(400,"تاريخ الانتهاء غير صالح")
    b=ActivationCodeBatch(name=name.strip()[:160] or f"Batch {datetime.utcnow():%Y%m%d}",course_id=course_id,quantity=qty,distributor=distributor.strip()[:180],notes=notes.strip()[:2000],expires_at=expiry,active=True,created_by=u.id)
    db.add(b); db.flush()
    prefix=f"R{course_id:02d}B{b.id:04d}"
    for i in range(1,qty+1):
        value=f"{prefix}-{secrets.token_hex(4).upper()}"
        while db.query(ActivationCode).filter_by(code=value).first(): value=f"{prefix}-{secrets.token_hex(4).upper()}"
        ac=ActivationCode(code=value,course_id=course_id,max_uses=1,used_count=0,active=True,expires_at=expiry); db.add(ac); db.flush(); db.add(ActivationCodeInventory(batch_id=b.id,activation_code_id=ac.id,serial_no=i))
    db.commit(); audit(db,request,u,"activation_code_batch_created",{"batch_id":b.id,"quantity":qty,"course_id":course_id,"distributor":b.distributor})
    return RedirectResponse(f"/admin/code-inventory/{b.id}",303)

@router.get("/admin/code-inventory/{batch_id}", response_class=HTMLResponse)
def admin_code_batch_detail(batch_id:int,request:Request,db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","accounting"); b=db.get(ActivationCodeBatch,batch_id)
    if not b: raise HTTPException(404)
    rows=_activation_batch_rows(db,b.id); now=datetime.utcnow(); detail=[]
    redemptions={r.activation_code_id:r for r in db.query(ActivationRedemption).filter(ActivationRedemption.activation_code_id.in_([c.id for _,c in rows if c])).all()} if rows else {}
    user_ids=[r.user_id for r in redemptions.values()]; users={u.id:u for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    for inv,c in rows:
        if not c: continue
        status="used" if c.used_count>=c.max_uses else ("expired" if c.expires_at and c.expires_at<=now else ("available" if c.active else "disabled")); red=redemptions.get(c.id)
        detail.append({"inv":inv,"code":c,"status":status,"redemption":red,"user":users.get(red.user_id) if red else None})
    metrics={k:sum(1 for x in detail if x["status"]==k) for k in ["available","used","expired","disabled"]}
    return render_template("admin_code_batch.html",ctx(request,db,batch=b,course=db.get(Course,b.course_id),rows=detail,metrics=metrics))

@router.post("/admin/code-inventory/{batch_id}/toggle")
def admin_code_batch_toggle(batch_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","accounting")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    b=db.get(ActivationCodeBatch,batch_id)
    if not b: raise HTTPException(404)
    b.active=not b.active
    for _,c in _activation_batch_rows(db,b.id):
        if c and c.used_count<c.max_uses: c.active=b.active
    db.commit(); audit(db,request,u,"activation_code_batch_toggled",{"batch_id":b.id,"active":b.active}); return RedirectResponse(f"/admin/code-inventory/{b.id}",303)

@router.post("/admin/code-inventory/{batch_id}/distributor")
def admin_code_batch_distributor(batch_id:int,request:Request,distributor:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","accounting")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    b=db.get(ActivationCodeBatch,batch_id)
    if not b: raise HTTPException(404)
    b.distributor=distributor.strip()[:180]; db.commit(); audit(db,request,u,"activation_code_batch_distributor_updated",{"batch_id":b.id,"distributor":b.distributor}); return RedirectResponse(f"/admin/code-inventory/{b.id}",303)

@router.get("/admin/code-inventory/export/{batch_id}.xlsx")
def admin_code_batch_xlsx(batch_id:int,request:Request,db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","accounting"); b=db.get(ActivationCodeBatch,batch_id)
    if not b: raise HTTPException(404)
    from openpyxl import Workbook
    wb=Workbook(); ws=wb.active; ws.title="Activation Codes"; ws.append(["Serial","Code","Course","Distributor","Status","Expires","Redeemed By","Redeemed At"]); now=datetime.utcnow(); course=db.get(Course,b.course_id)
    reds={r.activation_code_id:r for r in db.query(ActivationRedemption).filter(ActivationRedemption.activation_code_id.in_([c.id for _,c in _activation_batch_rows(db,b.id) if c])).all()}; uids=[r.user_id for r in reds.values()]; users={u.id:u for u in db.query(User).filter(User.id.in_(uids)).all()} if uids else {}
    for inv,c in _activation_batch_rows(db,b.id):
        if not c: continue
        red=reds.get(c.id); status="Used" if c.used_count>=c.max_uses else ("Expired" if c.expires_at and c.expires_at<=now else ("Available" if c.active else "Disabled")); usr=users.get(red.user_id) if red else None
        ws.append([inv.serial_no,c.code,course.title if course else str(b.course_id),b.distributor,status,c.expires_at.strftime('%Y-%m-%d %H:%M') if c.expires_at else "",usr.name if usr else "",red.redeemed_at.strftime('%Y-%m-%d %H:%M') if red else ""])
    out=io.BytesIO(); wb.save(out); out.seek(0); headers={"Content-Disposition":f'attachment; filename="activation-batch-{b.id}.xlsx"'}; return StreamingResponse(out,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers=headers)

@router.get("/admin/code-inventory/export/{batch_id}.pdf")
def admin_code_batch_pdf(batch_id:int,request:Request,db:Session=Depends(get_db)):
    require_role(request,db,"super_admin","admin","accounting"); b=db.get(ActivationCodeBatch,batch_id)
    if not b: raise HTTPException(404)
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    out=io.BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24); styles=getSampleStyleSheet(); story=[Paragraph(f"Activation Code Batch #{b.id} - {html.escape(b.name)}",styles['Title']),Spacer(1,8),Paragraph(f"Distributor: {html.escape(b.distributor or '-')} | Course ID: {b.course_id}",styles['Normal']),Spacer(1,10)]
    data=[["#","Code","Status","Expiry"]]; now=datetime.utcnow()
    for inv,c in _activation_batch_rows(db,b.id):
        if not c: continue
        status="USED" if c.used_count>=c.max_uses else ("EXPIRED" if c.expires_at and c.expires_at<=now else ("AVAILABLE" if c.active else "DISABLED")); data.append([str(inv.serial_no),c.code,status,c.expires_at.strftime('%Y-%m-%d') if c.expires_at else '-'])
    t=Table(data,repeatRows=1,colWidths=[35,245,80,90]); t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.grey),('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'MIDDLE')])); story.append(t); doc.build(story); out.seek(0); return StreamingResponse(out,media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="activation-batch-{b.id}.pdf"'})

@router.post("/activate-code")
def redeem_activation(request:Request,code:str=Form(...),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"student")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    ac, status = redeem_code(db, user_id=u.id, raw_code=code)
    if status == "invalid": raise HTTPException(400,"الكود غير صالح أو انتهت صلاحيته")
    if status == "already_used": raise HTTPException(409,"تم استخدام هذا الكود من قبل")
    award_points(db,u.id,5,"تفعيل كورس","activation",ac.id)
    db.commit(); audit(db,request,u,"activation_code_redeemed",{"course_id":ac.course_id})
    return RedirectResponse(f"/course/{ac.course_id}",303)

@router.post("/admin/activation-codes")
def activation_code_create(request:Request,course_id:int=Form(...),code:str=Form(""),max_uses:int=Form(1),expires_at:str=Form(""),csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","accounting")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    if not db.get(Course,course_id): raise HTTPException(404)
    value=(code.strip().upper() or secrets.token_hex(6).upper())[:48]
    if db.query(ActivationCode).filter(func.upper(ActivationCode.code)==value).first(): raise HTTPException(409,"الكود موجود بالفعل")
    expiry=None
    if expires_at.strip():
        try: expiry=datetime.fromisoformat(expires_at.strip())
        except ValueError: raise HTTPException(400,"تاريخ انتهاء كود التفعيل غير صالح")
    db.add(ActivationCode(code=value,course_id=course_id,max_uses=max(1,min(max_uses,10000)),active=True,expires_at=expiry));db.commit();audit(db,request,u,"activation_code_created",{"code":value,"course_id":course_id,"expires_at":expiry.isoformat() if expiry else None})
    return RedirectResponse("/admin/commerce",303)

@router.post("/admin/activation-codes/{code_id}/toggle")
def activation_code_toggle(code_id:int,request:Request,csrf:str=Form(...),db:Session=Depends(get_db)):
    u=require_role(request,db,"super_admin","admin","accounting")
    if not check_csrf(request.session,csrf): raise HTTPException(403)
    ac=db.get(ActivationCode,code_id)
    if not ac: raise HTTPException(404)
    ac.active=not ac.active; db.commit(); audit(db,request,u,"activation_code_toggled",{"code_id":ac.id,"active":ac.active})
    return RedirectResponse("/admin/commerce",303)

