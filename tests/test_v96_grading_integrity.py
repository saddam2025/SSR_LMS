from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Course, Question, Quiz, QuizQuestionSetting
from app.services.quiz_grading import grade_answers, normalize_answer, total_points


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_weighted_quiz_grading_respects_configured_points():
    db = _session()
    c = Course(title="Weighted", grade="G", published=True)
    db.add(c); db.flush()
    qz = Quiz(course_id=c.id, title="Weighted exam", published=True)
    db.add(qz); db.flush()
    rows = [
        Question(quiz_id=qz.id, text="Q1", option_a="a", option_b="b", option_c="c", option_d="d", correct="A"),
        Question(quiz_id=qz.id, text="Q2", option_a="a", option_b="b", option_c="c", option_d="d", correct="B"),
        Question(quiz_id=qz.id, text="Q3", option_a="a", option_b="b", option_c="c", option_d="d", correct="C"),
    ]
    db.add_all(rows); db.flush()
    db.add_all([
        QuizQuestionSetting(question_id=rows[0].id, position=1, points=2),
        QuizQuestionSetting(question_id=rows[1].id, position=2, points=3),
        QuizQuestionSetting(question_id=rows[2].id, position=3, points=5),
    ])
    db.commit()
    result = grade_answers(db, rows, {str(rows[0].id): "A", str(rows[1].id): "A", str(rows[2].id): "C"})
    assert total_points(db, rows) == 10
    assert result["score"] == 7
    assert result["total"] == 10
    assert result["percentage"] == 70.0
    assert result["correct_count"] == 2
    assert [d["awarded_points"] for d in result["details"]] == [2, 0, 5]


def test_invalid_answer_payload_is_not_silently_truncated_to_correct_choice():
    assert normalize_answer("A") == "A"
    assert normalize_answer(" a ") == "A"
    assert normalize_answer("A-anything") == ""
    assert normalize_answer("E") == ""
    assert normalize_answer("") == ""
