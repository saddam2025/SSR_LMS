from datetime import datetime, timezone
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, Text, Float, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(190), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    mfa_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[str] = mapped_column(String(50), default="الصف الأول الثانوي", index=True)
    price: Mapped[float] = mapped_column(Float, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    teacher_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lessons = relationship("Lesson", back_populates="course", cascade="all, delete-orphan")



class CourseAcademicPeriod(Base):
    __tablename__ = "course_academic_periods"
    __table_args__ = (UniqueConstraint("course_id", name="uq_course_academic_period_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    academic_year: Mapped[str] = mapped_column(String(20), default="2026/2027", index=True)
    term: Mapped[str] = mapped_column(String(30), default="الترم الأول", index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CourseCompletionPolicy(Base):
    __tablename__ = "course_completion_policies"
    __table_args__ = (UniqueConstraint("course_id", name="uq_course_completion_policy_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    require_all_lessons: Mapped[bool] = mapped_column(Boolean, default=True)
    minimum_quiz_average: Mapped[int] = mapped_column(Integer, default=60)
    minimum_homework_average: Mapped[int] = mapped_column(Integer, default=60)
    require_quizzes: Mapped[bool] = mapped_column(Boolean, default=False)
    require_homeworks: Mapped[bool] = mapped_column(Boolean, default=False)
    certificate_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class CourseCertificate(Base):
    __tablename__ = "course_certificates"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_course_certificate_user_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    verification_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    final_score: Mapped[float] = mapped_column(Float, default=0)
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    revoked_reason: Mapped[str] = mapped_column(String(300), default="")

Index("ix_course_certificate_verify", CourseCertificate.verification_code, CourseCertificate.revoked_at)

class RevisionPlan(Base):
    __tablename__ = "revision_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[str] = mapped_column(String(80), default="الصف الثالث الثانوي", index=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    exam_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class RevisionTask(Base):
    __tablename__ = "revision_tasks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("revision_plans.id", ondelete="CASCADE"), index=True)
    day_number: Mapped[int] = mapped_column(Integer, default=1, index=True)
    order_index: Mapped[int] = mapped_column(Integer, default=1, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    content_type: Mapped[str] = mapped_column(String(20), default="note", index=True)
    content_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class RevisionTaskProgress(Base):
    __tablename__ = "revision_task_progress"
    __table_args__ = (UniqueConstraint("user_id", "task_id", name="uq_revision_task_progress"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("revision_tasks.id", ondelete="CASCADE"), index=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

Index("ix_revision_plan_grade_publish", RevisionPlan.grade, RevisionPlan.published)
Index("ix_revision_task_plan_day", RevisionTask.plan_id, RevisionTask.day_number, RevisionTask.order_index)

class CourseCategory(Base):
    __tablename__ = "course_categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(140), unique=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    grade: Mapped[str] = mapped_column(String(80), default="", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class CourseCategoryAssignment(Base):
    __tablename__ = "course_category_assignments"
    __table_args__ = (UniqueConstraint("course_id", name="uq_course_category_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("course_categories.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

Index("ix_course_categories_active_sort", CourseCategory.active, CourseCategory.sort_order)



class ContentUnit(Base):
    __tablename__ = "content_units"
    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_content_unit_course_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    order_index: Mapped[int] = mapped_column(Integer, default=1, index=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class LessonUnitAssignment(Base):
    __tablename__ = "lesson_unit_assignments"
    __table_args__ = (UniqueConstraint("lesson_id", name="uq_lesson_unit_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("content_units.id", ondelete="CASCADE"), index=True)

class QuizUnitAssignment(Base):
    __tablename__ = "quiz_unit_assignments"
    __table_args__ = (UniqueConstraint("quiz_id", name="uq_quiz_unit_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("content_units.id", ondelete="CASCADE"), index=True)

class HomeworkUnitAssignment(Base):
    __tablename__ = "homework_unit_assignments"
    __table_args__ = (UniqueConstraint("homework_id", name="uq_homework_unit_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    homework_id: Mapped[int] = mapped_column(ForeignKey("homeworks.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("content_units.id", ondelete="CASCADE"), index=True)

Index("ix_content_units_course_order", ContentUnit.course_id, ContentUnit.order_index)

class ContentSchedule(Base):
    __tablename__ = "content_schedules"
    __table_args__ = (UniqueConstraint("content_type", "content_id", name="uq_content_schedule_target"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_type: Mapped[str] = mapped_column(String(20), index=True)
    content_id: Mapped[int] = mapped_column(Integer, index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("ix_content_schedule_target", ContentSchedule.content_type, ContentSchedule.content_id)

class LessonDripRule(Base):
    __tablename__ = "lesson_drip_rules"
    __table_args__ = (UniqueConstraint("lesson_id", name="uq_lesson_drip_rule"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(30), default="previous", index=True)
    delay_days: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class LessonAccessOverride(Base):
    __tablename__ = "lesson_access_overrides"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_access_override"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(12), default="unlock", index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("ix_lesson_access_override_user_lesson", LessonAccessOverride.user_id, LessonAccessOverride.lesson_id)

class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, default="")
    video_url: Mapped[str] = mapped_column(String(500), default="")
    order_index: Mapped[int] = mapped_column(Integer, default=1)
    published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    course = relationship("Course", back_populates="lessons")

class LessonVideoProfile(Base):
    __tablename__ = "lesson_video_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, index=True)
    provider: Mapped[str] = mapped_column(String(40), default="external")
    stream_type: Mapped[str] = mapped_column(String(20), default="auto")
    drm_mode: Mapped[str] = mapped_column(String(30), default="none")
    processing_status: Mapped[str] = mapped_column(String(20), default="ready", index=True)
    thumbnail_url: Mapped[str] = mapped_column(String(500), default="")
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("user_id", "course_id", name="uq_enrollment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    watched_seconds: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class Quiz(Base):
    __tablename__ = "quizzes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, default=30)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True)

class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(255))
    option_b: Mapped[str] = mapped_column(String(255))
    option_c: Mapped[str] = mapped_column(String(255))
    option_d: Mapped[str] = mapped_column(String(255))
    correct: Mapped[str] = mapped_column(String(1))


class QuestionBankItem(Base):
    __tablename__ = "question_bank_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    text: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(255))
    option_b: Mapped[str] = mapped_column(String(255))
    option_c: Mapped[str] = mapped_column(String(255))
    option_d: Mapped[str] = mapped_column(String(255))
    correct: Mapped[str] = mapped_column(String(1))
    default_points: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class QuizQuestionSetting(Base):
    __tablename__ = "quiz_question_settings"
    __table_args__ = (UniqueConstraint("question_id", name="uq_quiz_question_setting"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=1, index=True)
    points: Mapped[int] = mapped_column(Integer, default=1)

Index("ix_qbank_course_created", QuestionBankItem.course_id, QuestionBankItem.created_at)
Index("ix_quiz_question_position", QuizQuestionSetting.position, QuizQuestionSetting.question_id)


class QuestionBankTaxonomy(Base):
    __tablename__ = "question_bank_taxonomy"
    __table_args__ = (UniqueConstraint("bank_item_id", name="uq_qbank_taxonomy_item"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_item_id: Mapped[int] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", index=True)

class QuestionTaxonomy(Base):
    __tablename__ = "question_taxonomy"
    __table_args__ = (UniqueConstraint("question_id", name="uq_question_taxonomy_question"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True, index=True)
    difficulty: Mapped[str] = mapped_column(String(20), default="medium", index=True)

class MockExamProfile(Base):
    __tablename__ = "mock_exam_profiles"
    __table_args__ = (UniqueConstraint("quiz_id", name="uq_mock_exam_quiz"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id", ondelete="CASCADE"), index=True)
    source_unit_id: Mapped[int | None] = mapped_column(ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True, index=True)
    difficulty_filter: Mapped[str] = mapped_column(String(20), default="all", index=True)
    requested_questions: Mapped[int] = mapped_column(Integer, default=20)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class MockExamAttemptAnalysis(Base):
    __tablename__ = "mock_exam_attempt_analyses"
    __table_args__ = (UniqueConstraint("attempt_id", name="uq_mock_exam_attempt_analysis"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True)
    analysis_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    total: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="in_progress", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    payment_ref: Mapped[str] = mapped_column(String(120), default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=0)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint_hash", name="uq_user_device"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), index=True)
    label: Mapped[str] = mapped_column(String(180), default="Unknown device")
    last_ip: Mapped[str] = mapped_column(String(80), default="")
    trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ActiveSession(Base):
    __tablename__ = "active_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), nullable=True, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ip: Mapped[str] = mapped_column(String(80), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(160), index=True)
    ip: Mapped[str] = mapped_column(String(80), default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_sessions_user_active", ActiveSession.user_id, ActiveSession.revoked_at)


class PaymentTransaction(Base):
    __tablename__ = "payment_transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    provider: Mapped[str] = mapped_column(String(30), default="paymob", index=True)
    merchant_reference: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    provider_reference: Mapped[str] = mapped_column(String(160), default="", index=True)
    amount: Mapped[float] = mapped_column(Float, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="EGP")
    coupon_code: Mapped[str] = mapped_column(String(40), default="")
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"
    __table_args__ = (UniqueConstraint("coupon_id", "user_id", "course_id", name="uq_coupon_redemption"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    coupon_id: Mapped[int] = mapped_column(ForeignKey("coupons.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payment_transactions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class StudentAttendance(Base):
    __tablename__ = "student_attendance"
    __table_args__ = (UniqueConstraint("user_id", "attendance_date", name="uq_student_attendance_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    attendance_date: Mapped[str] = mapped_column(String(10), index=True)
    status: Mapped[str] = mapped_column(String(20), default="present", index=True)
    source: Mapped[str] = mapped_column(String(30), default="manual", index=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    marked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("ix_attendance_date_status", StudentAttendance.attendance_date, StudentAttendance.status)

class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(30), default="info", index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PushDevice(Base):
    __tablename__ = "push_devices"
    __table_args__ = (UniqueConstraint("push_token", name="uq_push_device_token"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(20), default="android", index=True)
    push_token: Mapped[str] = mapped_column(String(2048), unique=True)
    installation_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    device_name: Mapped[str] = mapped_column(String(180), default="Android")
    app_version: Mapped[str] = mapped_column(String(40), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_push_device_user_active", PushDevice.user_id, PushDevice.active)

class CommunicationCampaign(Base):
    __tablename__ = "communication_campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text, default="")
    audience_type: Mapped[str] = mapped_column(String(30), default="all_students", index=True)
    audience_value: Mapped[str] = mapped_column(String(120), default="")
    channels: Mapped[str] = mapped_column(String(120), default="in_app")
    recipient_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class CommunicationDelivery(Base):
    __tablename__ = "communication_deliveries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("communication_campaigns.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    channel: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    detail: Mapped[str] = mapped_column(String(500), default="")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_communication_campaign_created", CommunicationCampaign.created_at, CommunicationCampaign.audience_type)
Index("ix_communication_delivery_campaign_status", CommunicationDelivery.campaign_id, CommunicationDelivery.status, CommunicationDelivery.channel)

class MediaAsset(Base):
    __tablename__ = "media_assets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True, index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(30), default="local")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ParentStudent(Base):
    __tablename__ = "parent_students"
    __table_args__ = (UniqueConstraint("parent_id", "student_id", name="uq_parent_student"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class Homework(Base):
    __tablename__ = "homeworks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    lesson_id: Mapped[int | None] = mapped_column(ForeignKey("lessons.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    instructions: Mapped[str] = mapped_column(Text, default="")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"
    __table_args__ = (UniqueConstraint("homework_id", "student_id", name="uq_homework_submission"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    homework_id: Mapped[int] = mapped_column(ForeignKey("homeworks.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answer_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="submitted", index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    graded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

class StudentProfile(Base):
    __tablename__ = "student_profiles"
    __table_args__ = (UniqueConstraint("user_id", name="uq_student_profile_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    phone: Mapped[str] = mapped_column(String(30), default="", index=True)
    father_phone: Mapped[str] = mapped_column(String(30), default="")
    mother_phone: Mapped[str] = mapped_column(String(30), default="")
    school: Mapped[str] = mapped_column(String(180), default="")
    governorate: Mapped[str] = mapped_column(String(100), default="")
    grade: Mapped[str] = mapped_column(String(80), default="")
    section: Mapped[str] = mapped_column(String(80), default="")
    parent_job: Mapped[str] = mapped_column(String(120), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class OTPChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    phone: Mapped[str] = mapped_column(String(30), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(30), default="login", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class PointLedger(Base):
    __tablename__ = "point_ledger"
    __table_args__ = (UniqueConstraint("user_id", "reason", "ref_type", "ref_id", name="uq_point_award_ref"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    points: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(120), index=True)
    ref_type: Mapped[str] = mapped_column(String(40), default="")
    ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class DiscussionPost(Base):
    __tablename__ = "discussion_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("discussion_posts.id"), nullable=True, index=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="visible", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class ActivationCode(Base):
    __tablename__ = "activation_codes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ActivationCodeBatch(Base):
    __tablename__ = "activation_code_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    distributor: Mapped[str] = mapped_column(String(180), default="", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class ActivationCodeInventory(Base):
    __tablename__ = "activation_code_inventory"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("activation_code_batches.id"), index=True)
    activation_code_id: Mapped[int] = mapped_column(ForeignKey("activation_codes.id"), unique=True, index=True)
    serial_no: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class ActivationRedemption(Base):
    __tablename__ = "activation_redemptions"
    __table_args__ = (UniqueConstraint("activation_code_id", "user_id", name="uq_activation_user"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activation_code_id: Mapped[int] = mapped_column(ForeignKey("activation_codes.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    redeemed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Composite indexes for frequent production queries.
Index("ix_enrollments_user_active", Enrollment.user_id, Enrollment.active)
Index("ix_lesson_progress_user_completed", LessonProgress.user_id, LessonProgress.completed)
Index("ix_quiz_attempts_user_status_created", QuizAttempt.user_id, QuizAttempt.status, QuizAttempt.created_at)
Index("ix_notifications_user_read_created", Notification.user_id, Notification.read_at, Notification.created_at)
Index("ix_homework_submissions_student_status", HomeworkSubmission.student_id, HomeworkSubmission.status)
Index("ix_lessons_course_published_order", Lesson.course_id, Lesson.published, Lesson.order_index)
Index("ix_discussion_lesson_status_created", DiscussionPost.lesson_id, DiscussionPost.status, DiscussionPost.created_at)

class VocabularyItem(Base):
    __tablename__ = "vocabulary_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.id"), nullable=True, index=True)
    word: Mapped[str] = mapped_column(String(160), index=True)
    meaning_ar: Mapped[str] = mapped_column(String(300), default="")
    example: Mapped[str] = mapped_column(Text, default="")
    phonetic: Mapped[str] = mapped_column(String(120), default="")
    audio_us_url: Mapped[str] = mapped_column(String(500), default="")
    audio_uk_url: Mapped[str] = mapped_column(String(500), default="")
    level: Mapped[str] = mapped_column(String(30), default="general", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class VocabularyReview(Base):
    __tablename__ = "vocabulary_reviews"
    __table_args__ = (UniqueConstraint("user_id", "vocabulary_id", name="uq_vocab_review"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    vocabulary_id: Mapped[int] = mapped_column(ForeignKey("vocabulary_items.id"), index=True)
    box: Mapped[int] = mapped_column(Integer, default=1)
    streak: Mapped[int] = mapped_column(Integer, default=0)
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    next_review_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class StudentStreak(Base):
    __tablename__ = "student_streaks"
    __table_args__ = (UniqueConstraint("user_id", name="uq_student_streak"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    current_days: Mapped[int] = mapped_column(Integer, default=0)
    best_days: Mapped[int] = mapped_column(Integer, default=0)
    last_activity_date: Mapped[str] = mapped_column(String(10), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("ix_vocab_reviews_user_due", VocabularyReview.user_id, VocabularyReview.next_review_at)

# --- Interactive lesson experience (video checkpoints, smart study, offline policy) ---
class LessonCheckpoint(Base):
    __tablename__ = "lesson_checkpoints"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    timestamp_seconds: Mapped[int] = mapped_column(Integer, default=0, index=True)
    question: Mapped[str] = mapped_column(Text)
    option_a: Mapped[str] = mapped_column(String(255))
    option_b: Mapped[str] = mapped_column(String(255))
    option_c: Mapped[str] = mapped_column(String(255))
    option_d: Mapped[str] = mapped_column(String(255))
    correct: Mapped[str] = mapped_column(String(1))
    explanation: Mapped[str] = mapped_column(Text, default="")
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class CheckpointAttempt(Base):
    __tablename__ = "checkpoint_attempts"
    __table_args__ = (UniqueConstraint("checkpoint_id", "student_id", name="uq_checkpoint_student"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("lesson_checkpoints.id"), index=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    answer: Mapped[str] = mapped_column(String(1), default="")
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class LessonFlashcard(Base):
    __tablename__ = "lesson_flashcards"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    front: Mapped[str] = mapped_column(String(500))
    back: Mapped[str] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=1)
    published: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

class StudyAssistantLog(Base):
    __tablename__ = "study_assistant_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    source_kind: Mapped[str] = mapped_column(String(40), default="lesson_context", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class OfflineLessonPolicy(Base):
    __tablename__ = "offline_lesson_policies"
    __table_args__ = (UniqueConstraint("lesson_id", name="uq_offline_lesson_policy"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    provider_asset_id: Mapped[str] = mapped_column(String(255), default="")
    max_offline_days: Mapped[int] = mapped_column(Integer, default=7)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class OfflineGrant(Base):
    __tablename__ = "offline_grants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    lesson_id: Mapped[int] = mapped_column(ForeignKey("lessons.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    device_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

Index("ix_checkpoint_lesson_published_time", LessonCheckpoint.lesson_id, LessonCheckpoint.published, LessonCheckpoint.timestamp_seconds)
Index("ix_checkpoint_attempt_student_correct", CheckpointAttempt.student_id, CheckpointAttempt.is_correct)
Index("ix_flashcard_lesson_published_order", LessonFlashcard.lesson_id, LessonFlashcard.published, LessonFlashcard.order_index)
Index("ix_offline_grants_user_lesson_expiry", OfflineGrant.user_id, OfflineGrant.lesson_id, OfflineGrant.expires_at)


# --- Support tickets ---
class SupportTicket(Base):
    __tablename__ = "support_tickets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(180))
    category: Mapped[str] = mapped_column(String(40), default="technical", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)

class SupportTicketMessage(Base):
    __tablename__ = "support_ticket_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    is_staff: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_support_tickets_user_status_updated", SupportTicket.user_id, SupportTicket.status, SupportTicket.updated_at)
Index("ix_support_ticket_messages_ticket_created", SupportTicketMessage.ticket_id, SupportTicketMessage.created_at)

# --- UI V18: live classes and weekly schedule ---
class LiveClass(Base):
    __tablename__ = "live_classes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    provider: Mapped[str] = mapped_column(String(30), default="zoom", index=True)
    meeting_url: Mapped[str] = mapped_column(String(700), default="")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="scheduled", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class LiveClassAttendance(Base):
    __tablename__ = "live_class_attendance"
    __table_args__ = (UniqueConstraint("live_class_id", "user_id", name="uq_live_class_student"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    live_class_id: Mapped[int] = mapped_column(ForeignKey("live_classes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="present", index=True)
    joined_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    marked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

Index("ix_live_classes_course_time", LiveClass.course_id, LiveClass.scheduled_at)
Index("ix_live_attendance_class_status", LiveClassAttendance.live_class_id, LiveClassAttendance.status)


# --- UI V19: student groups and cohort management ---
class StudentGroup(Base):
    __tablename__ = "student_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    grade: Mapped[str] = mapped_column(String(80), default="", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class StudentGroupMembership(Base):
    __tablename__ = "student_group_memberships"
    __table_args__ = (UniqueConstraint("user_id", name="uq_student_one_group"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class GroupCourseAssignment(Base):
    __tablename__ = "group_course_assignments"
    __table_args__ = (UniqueConstraint("group_id", "course_id", name="uq_group_course"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class GroupLiveClassAssignment(Base):
    __tablename__ = "group_live_class_assignments"
    __table_args__ = (UniqueConstraint("live_class_id", name="uq_live_class_group"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("student_groups.id", ondelete="CASCADE"), index=True)
    live_class_id: Mapped[int] = mapped_column(ForeignKey("live_classes.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class StudentRemediationPlan(Base):
    __tablename__ = "student_remediation_plans"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    overall_score: Mapped[float] = mapped_column(Float, default=0)
    weak_units: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

class StudentRemediationItem(Base):
    __tablename__ = "student_remediation_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("student_remediation_plans.id", ondelete="CASCADE"), index=True)
    unit_id: Mapped[int | None] = mapped_column(ForeignKey("content_units.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(220))
    reason: Mapped[str] = mapped_column(String(500), default="")
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    target_type: Mapped[str] = mapped_column(String(20), default="note", index=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    target_url: Mapped[str] = mapped_column(String(500), default="")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

Index("ix_remediation_plan_user_active", StudentRemediationPlan.user_id, StudentRemediationPlan.active)
Index("ix_remediation_item_plan_priority", StudentRemediationItem.plan_id, StudentRemediationItem.priority, StudentRemediationItem.completed)


# --- Homepage V55: optional reels and honor roll ---
class HomepageFeature(Base):
    __tablename__ = "homepage_features"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

class HomepageReel(Base):
    __tablename__ = "homepage_reels"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    url: Mapped[str] = mapped_column(String(700))
    caption: Mapped[str] = mapped_column(String(300), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

class HomepageHonor(Base):
    __tablename__ = "homepage_honors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    student_name: Mapped[str] = mapped_column(String(140))
    grade: Mapped[str] = mapped_column(String(100), default="")
    rank_label: Mapped[str] = mapped_column(String(80), default="")
    score_text: Mapped[str] = mapped_column(String(80), default="")
    note: Mapped[str] = mapped_column(String(250), default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

Index("ix_homepage_reels_active_sort", HomepageReel.active, HomepageReel.sort_order, HomepageReel.id)
Index("ix_homepage_honors_active_sort", HomepageHonor.active, HomepageHonor.sort_order, HomepageHonor.id)
