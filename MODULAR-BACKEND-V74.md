# Modular Backend V74

V74 extracts identity administration into dedicated routers and services while preserving existing URL contracts.

- Users/Students: `app/routers/admin_users.py`
- Security Administration: `app/routers/admin_security.py`
- Parents: `app/routers/parents.py`
- User administration helpers: `app/services/user_admin.py`
- Student activity/attendance helper service: `app/services/student_activity.py`

`app/main.py` is now 2228 lines, down from 2614 in V73.

The remediation-specific route `/admin/students/{student_id}/learning-plan` intentionally remains with Learning Intelligence because its dependencies belong to the remediation engine, not account administration.
