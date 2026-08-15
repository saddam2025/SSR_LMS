import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..models import (
    Lesson, Quiz, LessonProgress, StudentRemediationPlan, StudentRemediationItem,
)
from .study_intelligence import student_learning_intelligence


def generate_remediation_plan(db: Session, user_id: int, force: bool = False):
    current = db.query(StudentRemediationPlan).filter_by(user_id=user_id, active=True).order_by(StudentRemediationPlan.id.desc()).first()
    if current and not force and current.generated_at and current.generated_at > datetime.utcnow() - timedelta(hours=24):
        return current
    intel = student_learning_intelligence(db, user_id)
    if current:
        current.active = False
    plan = StudentRemediationPlan(
        user_id=user_id, overall_score=intel["overall"], weak_units=len(intel["weak"]),
        summary_json=json.dumps({"weak":[r["unit"].name for r in intel["weak"]],"developing":[r["unit"].name for r in intel["developing"]],"strong":[r["unit"].name for r in intel["strong"][:3]]}, ensure_ascii=False),
    )
    db.add(plan); db.flush()
    lesson_ids=[lid for r in intel["units"] for lid in r["lesson_ids"]]
    quiz_ids=[qid for r in intel["units"] for qid in r["quiz_ids"]]
    lesson_map={x.id:x for x in db.query(Lesson).filter(Lesson.id.in_(lesson_ids or [-1])).all()}
    quiz_map={x.id:x for x in db.query(Quiz).filter(Quiz.id.in_(quiz_ids or [-1])).all()}
    for row in intel["units"]:
        if row["mastery"] >= 80:
            continue
        unit=row["unit"]
        priority="high" if row["mastery"] < 60 else "medium"
        reasons=[]
        if row["lesson_score"] is not None and row["lesson_score"] < 80: reasons.append(f"إكمال الدروس {row['lesson_score']:.0f}%")
        if row["quiz_score"] is not None and row["quiz_score"] < 70: reasons.append(f"الاختبارات {row['quiz_score']:.0f}%")
        if row["homework_score"] is not None and row["homework_score"] < 70: reasons.append(f"الواجبات {row['homework_score']:.0f}%")
        if row["mock_score"] is not None and row["mock_score"] < 70: reasons.append(f"الامتحان التجريبي {row['mock_score']:.0f}%")
        reason=" • ".join(reasons) or f"درجة الإتقان الحالية {row['mastery']:.0f}%"
        target_type="note"; target_id=None; target_url="/revision"; title=f"مراجعة {unit.name}"
        for lid in row["lesson_ids"]:
            lp=db.query(LessonProgress).filter_by(user_id=user_id, lesson_id=lid).first(); lesson=lesson_map.get(lid)
            if lesson and lesson.published and not (lp and lp.completed):
                target_type="lesson"; target_id=lid; target_url=f"/lesson/{lid}"; title=f"أكمل: {lesson.title}"; break
        if target_type == "note":
            for qid in row["quiz_ids"]:
                quiz=quiz_map.get(qid)
                if quiz and quiz.published:
                    target_type="quiz"; target_id=qid; target_url=f"/quiz/{qid}"; title=f"تدريب: {quiz.title}"; break
        db.add(StudentRemediationItem(plan_id=plan.id, unit_id=unit.id, title=title, reason=reason, priority=priority, target_type=target_type, target_id=target_id, target_url=target_url))
    if not intel["weak"] and not intel["developing"]:
        db.add(StudentRemediationItem(plan_id=plan.id, title="حافظ على مستواك الممتاز", reason="لا توجد نقاط ضعف واضحة حاليًا. استمر في خطة المراجعة والامتحانات التجريبية.", priority="low", target_type="revision", target_url="/revision"))
    db.commit()
    return plan


def remediation_context(db: Session, user_id: int, force: bool = False):
    intel=student_learning_intelligence(db, user_id)
    plan=generate_remediation_plan(db, user_id, force=force)
    items=db.query(StudentRemediationItem).filter_by(plan_id=plan.id).order_by(StudentRemediationItem.completed.asc(), StudentRemediationItem.priority.asc(), StudentRemediationItem.id).all()
    done=sum(1 for x in items if x.completed)
    return intel, plan, items, {"done":done,"total":len(items),"pct":round(done*100/len(items)) if items else 100}


def smart_tutor_recommendations(db: Session, user_id: int):
    intel=student_learning_intelligence(db, user_id)
    rows=[]
    for row in intel["units"]:
        if row["mastery"] >= 80:
            continue
        target=None
        for lid in row["lesson_ids"]:
            lesson=db.get(Lesson, lid); lp=db.query(LessonProgress).filter_by(user_id=user_id, lesson_id=lid).first()
            if lesson and lesson.published and not (lp and lp.completed):
                target=lesson; break
        if not target and row["lesson_ids"]:
            target=db.get(Lesson, row["lesson_ids"][0])
        rows.append({"unit":row["unit"],"course":row["course"],"mastery":row["mastery"],"level":row["level"],"lesson":target})
    return intel, rows[:6]
