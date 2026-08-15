# Mostashar V75 — Attendance / Live Classes / Groups Extraction

## Scope
V75 continues the modular backend migration by extracting the remaining attendance, live-class, and student-group domains from `app/main.py` without changing public URLs.

### New router
- `app/routers/community.py` — attendance center, student schedule/join, live-class administration, and student-group administration.

### New service
- `app/services/community.py` — attendance-row calculation, live-class eligibility, group membership/course synchronization, and safe live-meeting URL validation.

## Compatibility and security
- Existing HTTP paths and methods are preserved.
- Role checks and CSRF remain server-side through `request_context` and `security`.
- Student dashboard uses the same extracted `student_live_classes` service as `/schedule`, avoiding divergent access logic.
- Live meeting links remain HTTPS-only and provider-host constrained for Zoom, Meet, Teams, and YouTube.
- Group-scoped live classes remain restricted to members of the assigned group.

## Main.py reduction
- V74: 2228 lines
- V75: 1995 lines

## Verification
Passed locally:
- `tests/community_domains_v75.py`
- `tests/attendance_center_v16_flow.py`
- `tests/live_classes_v18_flow.py`
- `tests/groups_v19_flow.py`
- `tests/student_parent_attendance_v17_flow.py`
- `tests/navigation_contract.py`
- `tests/auth_http_contract_v53.py`
- `tests/media_integrity_v56.py`
- `tests/lecture_upload_v57.py`
- Python compile

No duplicate HTTP routes were detected.

## Production-only acceptance still required
Live integrations must still be exercised after deployment with production secrets/accounts (Cloudflare Stream/R2, Paymob, SMS/OTP providers, and real meeting-provider links).
