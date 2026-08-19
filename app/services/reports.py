import html, io, zipfile
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from ..models import User, Enrollment, QuizAttempt, HomeworkSubmission, StudentProfile, Homework

def student_performance_rows(db: Session, student_ids: list[int] | None = None):
    query = db.query(User).filter(User.role == "student", User.is_active == True)
    if student_ids is not None:
        ids = list(dict.fromkeys(int(x) for x in student_ids if int(x) > 0))
        if not ids:
            return []
        query = query.filter(User.id.in_(ids))
    students = query.order_by(User.name).all()
    student_ids = [s.id for s in students]
    enrollments = db.query(Enrollment).filter(Enrollment.user_id.in_(student_ids or [-1]), Enrollment.active == True).all()
    attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id.in_(student_ids or [-1]), QuizAttempt.status == "submitted").all()
    submissions = db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id.in_(student_ids or [-1])).all()
    profiles = {x.user_id: x for x in db.query(StudentProfile).filter(StudentProfile.user_id.in_(student_ids or [-1])).all()}
    course_ids = list({e.course_id for e in enrollments})
    homeworks = db.query(Homework).filter(Homework.course_id.in_(course_ids or [-1]), Homework.published == True).all()
    homework_by_course = {}
    for h in homeworks:
        homework_by_course.setdefault(h.course_id, []).append(h)
    now = datetime.utcnow()
    enroll_by_student, attempt_by_student, sub_by_student = {}, {}, {}
    for e in enrollments: enroll_by_student.setdefault(e.user_id, []).append(e)
    for a in attempts: attempt_by_student.setdefault(a.user_id, []).append(a)
    for x in submissions: sub_by_student.setdefault(x.student_id, []).append(x)
    rows = []
    for student in students:
        ens = enroll_by_student.get(student.id, [])
        ats = attempt_by_student.get(student.id, [])
        subs = sub_by_student.get(student.id, [])
        progress_avg = round(sum(int(e.progress or 0) for e in ens)/len(ens), 1) if ens else 0.0
        quiz_avg = round(sum(float(a.score or 0) for a in ats)/len(ats), 1) if ats else 0.0
        graded = [x for x in subs if x.score is not None]
        homework_avg = round(sum(float(x.score or 0) for x in graded)/len(graded), 1) if graded else 0.0
        relevant = []
        for e in ens: relevant.extend(homework_by_course.get(e.course_id, []))
        due = [h for h in relevant if h.due_at and h.due_at < now]
        submitted_ids = {x.homework_id for x in subs}
        missed = sum(1 for h in due if h.id not in submitted_ids)
        compliance = round(((len(due)-missed)/len(due))*100, 1) if due else 100.0
        late = sum(1 for x in subs for h in relevant if h.id == x.homework_id and h.due_at and x.submitted_at > h.due_at)
        signals, risk_points = [], 0
        if ens and progress_avg < 35: risk_points += 3; signals.append("تقدم منخفض")
        elif ens and progress_avg < 60: risk_points += 1; signals.append("التقدم يحتاج متابعة")
        if ats and quiz_avg < 50: risk_points += 3; signals.append("نتائج اختبارات منخفضة")
        elif ats and quiz_avg < 65: risk_points += 1; signals.append("متوسط اختبارات متوسط")
        if graded and homework_avg < 50: risk_points += 2; signals.append("درجات واجبات منخفضة")
        if missed >= 2: risk_points += 3; signals.append(f"{missed} واجبات فائتة")
        elif missed == 1: risk_points += 1; signals.append("واجب فائت")
        if late >= 2: risk_points += 1; signals.append("تأخر متكرر")
        if not ats and ens: risk_points += 1; signals.append("لا توجد اختبارات مكتملة")
        risk = "high" if risk_points >= 5 else ("medium" if risk_points >= 2 else "low")
        label = {"high":"يحتاج تدخل", "medium":"متابعة", "low":"مستقر"}[risk]
        rows.append({"student": student, "profile": profiles.get(student.id), "courses": len(ens), "progress_avg": progress_avg,
                     "quiz_avg": quiz_avg, "quiz_count": len(ats), "homework_avg": homework_avg, "homework_count": len(subs),
                     "missed": missed, "late": late, "compliance": compliance, "risk": risk, "risk_label": label, "signals": signals})
    return rows


def performance_candidate_student_ids(db: Session, limit: int = 400) -> list[int]:
    """Return a bounded set of students likely to need attention.

    The daily admin dashboard only renders a handful of risk rows. Scanning every
    student, quiz and homework on every dashboard request becomes O(total students).
    This preselection keeps the dashboard bounded while the full reports page can
    still compute all rows on demand.
    """
    limit = max(50, min(int(limit), 1000))
    out: list[int] = []
    seen: set[int] = set()

    def add(rows):
        for row in rows:
            if hasattr(row, "_mapping"):
                uid = int(next(iter(row._mapping.values())))
            elif isinstance(row, (tuple, list)):
                uid = int(row[0])
            else:
                uid = int(getattr(row, "user_id", getattr(row, "id", row)))
            if uid > 0 and uid not in seen:
                seen.add(uid); out.append(uid)
                if len(out) >= limit:
                    break

    low_progress = (
        db.query(Enrollment.user_id)
        .join(User, User.id == Enrollment.user_id)
        .filter(User.role == "student", User.is_active == True, Enrollment.active == True, Enrollment.progress < 60)
        .order_by(Enrollment.progress.asc(), Enrollment.user_id.asc())
        .limit(limit)
        .all()
    )
    add(low_progress)
    if len(out) < limit:
        avg_score = func.avg(QuizAttempt.score)
        low_quiz = (
            db.query(QuizAttempt.user_id)
            .join(User, User.id == QuizAttempt.user_id)
            .filter(User.role == "student", User.is_active == True, QuizAttempt.status == "submitted")
            .group_by(QuizAttempt.user_id)
            .having(avg_score < 65)
            .order_by(avg_score.asc())
            .limit(limit)
            .all()
        )
        add(low_quiz)
    if len(out) < min(limit, 120):
        recent = (
            db.query(User.id)
            .filter(User.role == "student", User.is_active == True)
            .order_by(User.id.desc())
            .limit(min(120, limit))
            .all()
        )
        add(recent)
    return out[:limit]

def pdf_arabic(value):
    """Minimal Arabic shaping for ReportLab environments without browser-style RTL shaping."""
    text_value = str(value or "")
    if not any("\u0600" <= ch <= "\u06ff" for ch in text_value):
        return text_value
    forms = {
        'ء':('ﺀ',None,None,None),'آ':('ﺁ','ﺂ',None,None),'أ':('ﺃ','ﺄ',None,None),'ؤ':('ﺅ','ﺆ',None,None),'إ':('ﺇ','ﺈ',None,None),
        'ئ':('ﺉ','ﺊ','ﺋ','ﺌ'),'ا':('ﺍ','ﺎ',None,None),'ب':('ﺏ','ﺐ','ﺑ','ﺒ'),'ة':('ﺓ','ﺔ',None,None),'ت':('ﺕ','ﺖ','ﺗ','ﺘ'),
        'ث':('ﺙ','ﺚ','ﺛ','ﺜ'),'ج':('ﺝ','ﺞ','ﺟ','ﺠ'),'ح':('ﺡ','ﺢ','ﺣ','ﺤ'),'خ':('ﺥ','ﺦ','ﺧ','ﺨ'),'د':('ﺩ','ﺪ',None,None),
        'ذ':('ﺫ','ﺬ',None,None),'ر':('ﺭ','ﺮ',None,None),'ز':('ﺯ','ﺰ',None,None),'س':('ﺱ','ﺲ','ﺳ','ﺴ'),'ش':('ﺵ','ﺶ','ﺷ','ﺸ'),
        'ص':('ﺹ','ﺺ','ﺻ','ﺼ'),'ض':('ﺽ','ﺾ','ﺿ','ﻀ'),'ط':('ﻁ','ﻂ','ﻃ','ﻄ'),'ظ':('ﻅ','ﻆ','ﻇ','ﻈ'),'ع':('ﻉ','ﻊ','ﻋ','ﻌ'),
        'غ':('ﻍ','ﻎ','ﻏ','ﻐ'),'ف':('ﻑ','ﻒ','ﻓ','ﻔ'),'ق':('ﻕ','ﻖ','ﻗ','ﻘ'),'ك':('ﻙ','ﻚ','ﻛ','ﻜ'),'ل':('ﻝ','ﻞ','ﻟ','ﻠ'),
        'م':('ﻡ','ﻢ','ﻣ','ﻤ'),'ن':('ﻥ','ﻦ','ﻧ','ﻨ'),'ه':('ﻩ','ﻪ','ﻫ','ﻬ'),'و':('ﻭ','ﻮ',None,None),'ى':('ﻯ','ﻰ',None,None),
        'ي':('ﻱ','ﻲ','ﻳ','ﻴ'),'ی':('ﯼ','ﯽ','ﯾ','ﯿ'),'پ':('ﭖ','ﭗ','ﭘ','ﭙ'),'چ':('ﭺ','ﭻ','ﭼ','ﭽ'),'ژ':('ﮊ','ﮋ',None,None),'گ':('ﮒ','ﮓ','ﮔ','ﮕ')
    }
    can_next = {ch for ch,f in forms.items() if f[2] is not None}
    can_prev = {ch for ch,f in forms.items() if f[1] is not None}
    chars=list(text_value); shaped=[]
    for i,ch in enumerate(chars):
        if ch not in forms: shaped.append(ch); continue
        prev = chars[i-1] if i>0 else ''
        nxt = chars[i+1] if i+1<len(chars) else ''
        join_prev = prev in can_next and ch in can_prev
        join_next = ch in can_next and nxt in can_prev
        f=forms[ch]
        shaped.append(f[3] if join_prev and join_next and f[3] else f[1] if join_prev and f[1] else f[2] if join_next and f[2] else f[0])
    return ''.join(shaped)[::-1]

def xlsx_col(n: int):
    out = ""
    while n:
        n, r = divmod(n-1, 26); out = chr(65+r) + out
    return out

def build_xlsx(headers, rows):
    def cell(ref, value, style=0):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
        txt = html.escape(str(value if value is not None else ""))
        return f'<c r="{ref}" t="inlineStr" s="{style}"><is><t>{txt}</t></is></c>'
    sheet_rows = ['<row r="1" ht="28" customHeight="1">'+''.join(cell(f'{xlsx_col(i+1)}1', v, 1) for i, v in enumerate(headers))+'</row>']
    for ri, row in enumerate(rows, 2):
        sheet_rows.append(f'<row r="{ri}">'+''.join(cell(f'{xlsx_col(i+1)}{ri}', v, 2 if i in {3,4,5,6} else 0) for i, v in enumerate(row))+'</row>')
    widths = [8,28,30,14,14,14,14,12,14,16,28]
    cols = ''.join(f'<col min="{i+1}" max="{i+1}" width="{w}" customWidth="1"/>' for i, w in enumerate(widths))
    sheet_xml = "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetViews><sheetView workbookViewId='0' rightToLeft='1'><pane ySplit='1' topLeftCell='A2' activePane='bottomLeft' state='frozen'/></sheetView></sheetViews><cols>" + cols + "</cols><sheetData>" + ''.join(sheet_rows) + "</sheetData><autoFilter ref='A1:K" + str(len(rows)+1) + "'/></worksheet>"
    parts = {
        '[Content_Types].xml': "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'><Default Extension='rels' ContentType='application/vnd.openxmlformats-package.relationships+xml'/><Default Extension='xml' ContentType='application/xml'/><Override PartName='/xl/workbook.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml'/><Override PartName='/xl/worksheets/sheet1.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml'/><Override PartName='/xl/styles.xml' ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml'/></Types>",
        '_rels/.rels': "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument' Target='xl/workbook.xml'/></Relationships>",
        'xl/workbook.xml': "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'><sheets><sheet name='Student Performance' sheetId='1' r:id='rId1'/></sheets></workbook>",
        'xl/_rels/workbook.xml.rels': "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'><Relationship Id='rId1' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet' Target='worksheets/sheet1.xml'/><Relationship Id='rId2' Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles' Target='styles.xml'/></Relationships>",
        'xl/styles.xml': "<?xml version='1.0' encoding='UTF-8' standalone='yes'?><styleSheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><fonts count='2'><font><sz val='11'/><name val='Arial'/></font><font><b/><color rgb='FFFFFFFF'/><sz val='11'/><name val='Arial'/></font></fonts><fills count='3'><fill><patternFill patternType='none'/></fill><fill><patternFill patternType='gray125'/></fill><fill><patternFill patternType='solid'><fgColor rgb='FF071A35'/><bgColor indexed='64'/></patternFill></fill></fills><borders count='1'><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellXfs count='3'><xf numFmtId='0' fontId='0' fillId='0' borderId='0'/><xf numFmtId='0' fontId='1' fillId='2' borderId='0' applyAlignment='1'><alignment horizontal='center' vertical='center'/></xf><xf numFmtId='2' fontId='0' fillId='0' borderId='0' applyNumberFormat='1'><alignment horizontal='center'/></xf></cellXfs></styleSheet>",
        'xl/worksheets/sheet1.xml': sheet_xml,
    }
    bio = io.BytesIO()
    with zipfile.ZipFile(bio, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, content in parts.items(): z.writestr(name, content)
    bio.seek(0); return bio
