"""Central role and permission policy for the unified LMS release."""

STAFF_ROLES = {"super_admin", "admin", "content_manager", "support", "accounting"}
ADMIN_ROLES = {"super_admin", "admin"}
CONTENT_ROLES = {"super_admin", "admin", "content_manager"}
COMMERCE_ROLES = {"super_admin", "admin", "accounting"}
SUPPORT_ROLES = {"super_admin", "admin", "support"}
SECURITY_ROLES = {"super_admin", "admin"}
USER_ADMIN_ROLES = {"super_admin", "admin"}

ROLE_LABELS = {
    "super_admin": "المدير العام",
    "admin": "مدير المنصة",
    "content_manager": "مشرف المحتوى",
    "support": "الدعم الفني",
    "accounting": "الحسابات",
    "student": "طالب",
    "parent": "ولي أمر",
}

ALLOWED_ROLES = set(ROLE_LABELS)

def is_staff(role: str) -> bool:
    return role in STAFF_ROLES

def can_manage_course(role: str, *, teacher_id: int | None = None, user_id: int | None = None) -> bool:
    """Single-teacher LMS: content is owned by the platform, not by staff accounts."""
    return role in CONTENT_ROLES
