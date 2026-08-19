from __future__ import annotations

from collections.abc import Mapping, Sequence
from sqlalchemy.orm import Session

from ..models import Question, QuizQuestionSetting

_VALID = {"A", "B", "C", "D"}


def normalize_answer(value) -> str:
    selected = str(value or "").strip().upper()
    return selected if selected in _VALID else ""


def question_settings(db: Session, questions: Sequence[Question]) -> dict[int, QuizQuestionSetting]:
    ids = [q.id for q in questions]
    if not ids:
        return {}
    return {
        row.question_id: row
        for row in db.query(QuizQuestionSetting).filter(QuizQuestionSetting.question_id.in_(ids)).all()
    }


def total_points(db: Session, questions: Sequence[Question]) -> int:
    settings = question_settings(db, questions)
    return sum(max(1, int(settings.get(q.id).points if settings.get(q.id) else 1)) for q in questions)


def grade_answers(db: Session, questions: Sequence[Question], answers: Mapping) -> dict:
    """Grade MCQ answers using each question's configured point weight.

    Invalid/non-single-letter answers are treated as unanswered. The return shape is
    shared by browser and API runtimes so they cannot drift apart.
    """
    settings = question_settings(db, questions)
    score = 0
    correct_count = 0
    details = []
    total = 0
    for q in questions:
        points = max(1, int(settings.get(q.id).points if settings.get(q.id) else 1))
        total += points
        selected = normalize_answer(answers.get(str(q.id), answers.get(q.id, "")))
        correct = normalize_answer(q.correct)
        is_correct = bool(selected and selected == correct)
        awarded = points if is_correct else 0
        if is_correct:
            correct_count += 1
            score += points
        options = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
        details.append({
            "question_id": q.id,
            "question": q.text,
            "selected": selected,
            "selected_text": options.get(selected, "لم تتم الإجابة"),
            "correct": correct,
            "correct_text": options.get(correct, ""),
            "is_correct": is_correct,
            "points": points,
            "awarded_points": awarded,
        })
    percentage = (score / total * 100.0) if total else 0.0
    return {
        "score": score,
        "total": total,
        "percentage": percentage,
        "correct_count": correct_count,
        "question_count": len(questions),
        "details": details,
    }
