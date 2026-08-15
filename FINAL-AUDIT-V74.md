# Mostashar V74 — Admin Identity Domains Extraction

## Scope
V74 continues the modular backend migration by extracting administrative identity domains from `app/main.py` without changing public URLs.

### New routers
- `app/routers/admin_users.py` — users, students, bulk import/actions, enrollment/status, Student 360.
- `app/routers/admin_security.py` — device blocking and active-session revocation.
- `app/routers/parents.py` — parent dashboard and parent/student linking.

### New services
- `app/services/user_admin.py` — student-group assignment, CSV/XLSX import parsing, password policy reuse, session revocation.
- `app/services/student_activity.py` — reusable student activity and weekly-attendance calculations.

## Compatibility
- Existing HTTP paths and methods are preserved.
- Session/role checks remain server-side through `request_context`.
- CSRF remains required on all administrative mutations.
- Deactivation/password reset/MFA reset continue to revoke active sessions.
- `/admin/students/{student_id}/learning-plan` remains with the learning-intelligence/remediation domain intentionally.

## Main.py reduction
- V73: 2614 lines
- V74: 2228 lines

## Verification
Passed locally:
- `tests/admin_domains_v74.py`
- `tests/student_management_v20_flow.py`
- `tests/final_parent_flow.py`
- `tests/support_student360_flow.py`
- `tests/security_smoke.py`
- `tests/auth_http_contract_v53.py`
- `tests/request_context_v66.py`
- `tests/student_reports_v13_flow.py`
- `tests/navigation_contract.py`
- `tests/learning_runtime_decoupling_v72.py`
- `tests/media_integrity_v56.py`
- `tests/lecture_upload_v57.py`
- `tests/auth_router_v68.py`
- Python compileall

No duplicate HTTP routes were detected.

## Production-only acceptance still required
Live integrations must still be exercised after deployment with production secrets/accounts (Cloudflare Stream/R2, Paymob, SMS/OTP providers).
