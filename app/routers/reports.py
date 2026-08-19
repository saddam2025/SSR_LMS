import io, os
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from ..db import get_db
from ..request_context import require_role, template_context
from ..services.template_rendering import render_template
from ..services.reports import student_performance_rows, build_xlsx, pdf_arabic

router = APIRouter()

@router.get('/admin/reports', response_class=HTMLResponse)
def admin_student_reports(request: Request, risk: str='all', page: int=1, page_size: int=100, db: Session=Depends(get_db)):
    require_role(request, db, 'super_admin','admin','content_manager','support')
    # Compute the report dataset once, but never render thousands of table rows into
    # a single HTML response. Large DOMs were the main browser-side bottleneck as
    # student counts grew. Full Excel/PDF exports remain available on demand.
    rows=student_performance_rows(db)
    if risk in {'high','medium','low'}: rows=[r for r in rows if r['risk']==risk]
    elif risk != 'all': risk='all'
    quiz_rows=[r for r in rows if r['quiz_count']]
    total_filtered=len(rows)
    summary={'students':total_filtered,'high':sum(1 for r in rows if r['risk']=='high'),'medium':sum(1 for r in rows if r['risk']=='medium'),'avg_progress':round(sum(r['progress_avg'] for r in rows)/total_filtered,1) if total_filtered else 0,'avg_quiz':round(sum(r['quiz_avg'] for r in quiz_rows)/len(quiz_rows),1) if quiz_rows else 0}
    page_size=max(25,min(int(page_size or 100),200))
    total_pages=max(1,(total_filtered+page_size-1)//page_size)
    page=max(1,min(int(page or 1),total_pages))
    start=(page-1)*page_size
    visible_rows=rows[start:start+page_size]
    return render_template('admin_reports.html', template_context(request,db,rows=visible_rows,summary=summary,risk_filter=risk,page=page,page_size=page_size,total_pages=total_pages,total_filtered=total_filtered))

@router.get('/admin/reports.xlsx')
def admin_student_reports_xlsx(request: Request, db: Session=Depends(get_db)):
    require_role(request,db,'super_admin','admin','content_manager','support')
    rows=student_performance_rows(db)
    headers=['ID','الطالب','البريد','الكورسات','متوسط التقدم %','متوسط الاختبارات %','متوسط الواجبات %','الالتزام %','واجبات فائتة','حالة المتابعة','أسباب المتابعة']
    data=[[r['student'].id,r['student'].name,r['student'].email,r['courses'],r['progress_avg'],r['quiz_avg'],r['homework_avg'],r['compliance'],r['missed'],r['risk_label'],'، '.join(r['signals'])] for r in rows]
    return StreamingResponse(build_xlsx(headers,data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename=student-performance-report.xlsx'})

@router.get('/admin/reports.pdf')
def admin_student_reports_pdf(request: Request, db: Session=Depends(get_db)):
    require_role(request,db,'super_admin','admin','content_manager','support'); rows=student_performance_rows(db)
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfbase import pdfmetrics
        font='Helvetica'
        for path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','/usr/share/fonts/truetype/freefont/FreeSans.ttf'):
            if os.path.exists(path): pdfmetrics.registerFont(TTFont('ReportUnicode',path)); font='ReportUnicode'; break
        bio=io.BytesIO(); doc=SimpleDocTemplate(bio,pagesize=landscape(A4),rightMargin=22,leftMargin=22,topMargin=22,bottomMargin=22)
        styles=getSampleStyleSheet(); styles['Title'].fontName=font; styles['Normal'].fontName=font
        story=[Paragraph('Student Performance Report - Al Mostashar LMS',styles['Title']),Spacer(1,10)]
        data=[['ID','Student','Progress','Quiz','Homework','Compliance','Missed','Status']]
        data += [[r['student'].id,pdf_arabic(r['student'].name),f"{r['progress_avg']}%",f"{r['quiz_avg']}%",f"{r['homework_avg']}%",f"{r['compliance']}%",r['missed'],pdf_arabic(r['risk_label'])] for r in rows]
        table=Table(data,repeatRows=1,colWidths=[35,150,70,70,75,80,55,90])
        table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,-1),font),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#071a35')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),0.25,colors.HexColor('#d9e2ec')),('ALIGN',(0,0),(-1,-1),'CENTER'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f7f9fc')])]))
        story.append(table); doc.build(story); bio.seek(0)
        return StreamingResponse(bio,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename=student-performance-report.pdf'})
    except Exception as exc:
        raise HTTPException(500,'تعذر إنشاء تقرير PDF') from exc
