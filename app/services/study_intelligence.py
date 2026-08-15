import json
import re
from sqlalchemy.orm import Session
from ..models import (
    User, Lesson, Homework, LessonCheckpoint, LessonFlashcard, Enrollment, ContentUnit,
    Course, LessonUnitAssignment, QuizUnitAssignment, HomeworkUnitAssignment, LessonProgress,
    QuizAttempt, HomeworkSubmission, MockExamAttemptAnalysis,
)

def study_tokens(value: str) -> set[str]:
    stop = {"من","في","على","الى","إلى","عن","هو","هي","ما","ماذا","كيف","ليه","لماذا","the","a","an","is","are","of","to","in","on","and","or","what","how"}
    return {x for x in re.findall(r"[\w\u0600-\u06FF]+", (value or "").lower()) if len(x) >= 2 and x not in stop}

def student_learning_intelligence(db: Session, user_id: int):
    enrollments = db.query(Enrollment).filter(Enrollment.user_id == user_id, Enrollment.active == True).all()
    course_ids = [e.course_id for e in enrollments]
    units = db.query(ContentUnit).filter(ContentUnit.course_id.in_(course_ids or [-1])).order_by(ContentUnit.course_id, ContentUnit.order_index, ContentUnit.id).all()
    course_map = {c.id:c for c in db.query(Course).filter(Course.id.in_(course_ids or [-1])).all()}
    unit_rows = []
    all_component_scores = []
    lesson_assign = db.query(LessonUnitAssignment).filter(LessonUnitAssignment.unit_id.in_([u.id for u in units] or [-1])).all()
    quiz_assign = db.query(QuizUnitAssignment).filter(QuizUnitAssignment.unit_id.in_([u.id for u in units] or [-1])).all()
    hw_assign = db.query(HomeworkUnitAssignment).filter(HomeworkUnitAssignment.unit_id.in_([u.id for u in units] or [-1])).all()
    lessons_by_unit, quizzes_by_unit, hws_by_unit = {}, {}, {}
    for a in lesson_assign: lessons_by_unit.setdefault(a.unit_id, []).append(a.lesson_id)
    for a in quiz_assign: quizzes_by_unit.setdefault(a.unit_id, []).append(a.quiz_id)
    for a in hw_assign: hws_by_unit.setdefault(a.unit_id, []).append(a.homework_id)
    progress_map = {x.lesson_id:x for x in db.query(LessonProgress).filter(LessonProgress.user_id == user_id).all()}
    attempts = db.query(QuizAttempt).filter(QuizAttempt.user_id == user_id, QuizAttempt.status == "submitted").all()
    attempts_by_quiz = {}
    for a in attempts: attempts_by_quiz.setdefault(a.quiz_id, []).append(a)
    subs_by_hw = {x.homework_id:x for x in db.query(HomeworkSubmission).filter(HomeworkSubmission.student_id == user_id).all()}
    attempt_ids = [a.id for a in attempts]
    mock_unit_scores = {}
    for row in db.query(MockExamAttemptAnalysis).filter(MockExamAttemptAnalysis.attempt_id.in_(attempt_ids or [-1])).all():
        try: data = json.loads(row.analysis_json or "{}")
        except Exception: data = {}
        for x in data.get("by_unit", []):
            try: mock_unit_scores.setdefault(str(x.get("name") or ""), []).append(float(x.get("accuracy") or 0))
            except Exception: pass
    for unit in units:
        lesson_ids = lessons_by_unit.get(unit.id, [])
        quiz_ids = quizzes_by_unit.get(unit.id, [])
        hw_ids = hws_by_unit.get(unit.id, [])
        components = []
        lesson_score = None
        if lesson_ids:
            lesson_score = round(sum(1 for lid in lesson_ids if progress_map.get(lid) and progress_map[lid].completed) * 100 / len(lesson_ids), 1)
            components.append(("lessons", lesson_score, 0.20))
        quiz_pcts = []
        for qid in quiz_ids:
            vals = [float(a.score or 0) * 100 / max(1, int(a.total or 0)) for a in attempts_by_quiz.get(qid, []) if int(a.total or 0) > 0]
            if vals: quiz_pcts.append(max(vals))
        quiz_score = round(sum(quiz_pcts)/len(quiz_pcts),1) if quiz_pcts else None
        if quiz_score is not None: components.append(("quizzes", quiz_score, 0.35))
        hw_scores = [float(subs_by_hw[x].score) for x in hw_ids if x in subs_by_hw and subs_by_hw[x].score is not None]
        hw_score = round(sum(hw_scores)/len(hw_scores),1) if hw_scores else None
        if hw_score is not None: components.append(("homework", hw_score, 0.20))
        mock_scores = mock_unit_scores.get(unit.name, [])
        mock_score = round(sum(mock_scores)/len(mock_scores),1) if mock_scores else None
        if mock_score is not None: components.append(("mock", mock_score, 0.25))
        if components:
            weight = sum(w for _,_,w in components)
            mastery = round(sum(v*w for _,v,w in components)/weight,1)
        else:
            mastery = 0.0
        all_component_scores.append(mastery)
        level = "strong" if mastery >= 80 else ("developing" if mastery >= 60 else "weak")
        level_label = "نقطة قوة" if level == "strong" else ("يحتاج تثبيت" if level == "developing" else "يحتاج علاج")
        unit_rows.append({"unit":unit,"course":course_map.get(unit.course_id),"mastery":mastery,"level":level,"level_label":level_label,
                          "lesson_score":lesson_score,"quiz_score":quiz_score,"homework_score":hw_score,"mock_score":mock_score,
                          "lesson_ids":lesson_ids,"quiz_ids":quiz_ids,"homework_ids":hw_ids})
    course_progress = [float(e.progress or 0) for e in enrollments]
    unit_overall = sum(all_component_scores)/len(all_component_scores) if all_component_scores else 0
    progress_overall = sum(course_progress)/len(course_progress) if course_progress else 0
    overall = round(unit_overall*0.75 + progress_overall*0.25,1) if unit_rows else round(progress_overall,1)
    weak = [r for r in unit_rows if r["level"] == "weak"]
    developing = [r for r in unit_rows if r["level"] == "developing"]
    strong = sorted([r for r in unit_rows if r["level"] == "strong"], key=lambda x:-x["mastery"])
    return {"overall":overall,"units":sorted(unit_rows,key=lambda x:(x["mastery"], x["unit"].order_index)),
            "weak":weak,"developing":developing,"strong":strong,"enrollments":enrollments,"courses":course_map}

def smart_study_answer(db: Session, lesson: Lesson, question: str, user: User | None = None, mode: str = "explain") -> tuple[str, str]:
    question = (question or "").strip()[:1000]
    tokens = study_tokens(question)
    sources: list[tuple[str, str]] = []
    for part in re.split(r"[\n\r.!?؟]+", lesson.body or ""):
        part = part.strip()
        if len(part) >= 12: sources.append(("شرح الدرس", part[:900]))
    homeworks = db.query(Homework).filter(Homework.lesson_id == lesson.id, Homework.published == True).all()
    for h in homeworks:
        if h.instructions.strip(): sources.append((f"الواجب: {h.title}", h.instructions.strip()[:900]))
    checkpoints = db.query(LessonCheckpoint).filter_by(lesson_id=lesson.id, published=True).all()
    for cp in checkpoints:
        if cp.explanation.strip(): sources.append(("تفسير سؤال تفاعلي", cp.explanation.strip()[:900]))
    cards = db.query(LessonFlashcard).filter_by(lesson_id=lesson.id, published=True).all()
    for card in cards: sources.append((f"Flashcard: {card.front}", card.back.strip()[:900]))
    ranked = []
    for kind, text_value in sources:
        score = len(tokens & study_tokens(text_value))
        if "واجب" in question and kind.startswith("الواجب"): score += 3
        ranked.append((score, kind, text_value))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    chosen = [x for x in ranked if x[0] > 0][:3] or ranked[:3]
    if not chosen:
        return ("لا يوجد محتوى نصي كافٍ في هذا الدرس للإجابة بدقة. اكتب سؤالك بعد إضافة شرح الدرس أو الـFlashcards أو تعليمات الواجب.", "no_context")
    personal_note = ""
    if user and user.role == "student":
        try:
            intel = student_learning_intelligence(db, user.id)
            assignment = db.query(LessonUnitAssignment).filter_by(lesson_id=lesson.id).first()
            unit_row = next((r for r in intel["units"] if assignment and r["unit"].id == assignment.unit_id), None)
            if unit_row: personal_note = f"مستواك الحالي في {unit_row['unit'].name}: {unit_row['mastery']:.0f}% — {unit_row['level_label']}."
        except Exception:
            personal_note = ""
    mode = (mode or "explain").strip().lower()
    labels = {"explain":"شرح مبسط مخصص لمستواك", "review":"مراجعة مركزة لمستواك", "practice":"تدريب موجه", "homework":"استعداد للواجب"}
    lines = [labels.get(mode, labels["explain"])]
    if personal_note: lines.append(f"• {personal_note}")
    if mode == "practice": lines.append("• قبل الحل: حاول الإجابة بنفسك، ثم ارجع للنقاط التالية فقط عند الحاجة.")
    elif mode == "review": lines.append("• ركّز على النقاط التالية كمراجعة قصيرة قبل الاختبار.")
    elif mode == "homework": lines.append("• استخدم النقاط التالية كتمهيد للحل، وليس كبديل عن محاولتك الشخصية.")
    else: lines.append("• الشرح التالي مبني فقط على محتوى الدرس الذي أضافه مستر رجب صديق.")
    for _, kind, txt in chosen: lines.append(f"• {kind}: {txt}")
    if checkpoints: lines.append("• بعد المراجعة جرّب أسئلة التوقف التفاعلية للتأكد من الفهم.")
    if personal_note and user: lines.append("• خطتك العلاجية تتحدث تلقائيًا من نتائجك؛ افتح /learning-plan لمتابعة الأولويات.")
    return ("\n".join(lines), f"personalized_{mode}" if personal_note else "lesson_context")
