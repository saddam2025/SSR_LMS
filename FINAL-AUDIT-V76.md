# Mostashar V76 — Bootstrap Cleanup & Academic Domains Extraction

## Scope
V76 continues the modular-backend migration from V75 without changing public URLs. The goal of this release is to remove public-homepage, content-center, revision-plan, and remediation/smart-tutor responsibilities from `app/main.py` and place them behind domain routers/services.

## Extracted domains

### Homepage
- `app/routers/homepage.py`
- `app/services/homepage.py`
- Public `/` route and `/admin/homepage*` routes moved out of `main.py`.
- Reel URLs remain restricted to HTTPS and the supported Instagram/Facebook/TikTok/YouTube hosts.
- Anonymous homepage rendering still avoids creating a session/CSRF cookie so Cloudflare edge caching remains possible.

### Academic content and revision
- `app/routers/academic_content.py`
- `app/services/academic_content.py`
- `/teacher/content*`, `/teacher/revision*`, and `/revision*` moved out of `main.py`.
- Content units, unit assignment, scheduling, period metadata, cloning, revision plans/tasks and student completion behavior keep the existing URLs and authorization/CSRF contracts.

### Remediation and Smart Tutor
- `app/routers/remediation.py`
- `app/services/remediation.py`
- `/smart-tutor`, `/learning-plan*`, and `/admin/students/{student_id}/learning-plan` moved out of `main.py`.
- Learning intelligence remains sourced from the existing `services/study_intelligence.py`; V76 separates plan generation/persistence and routing without duplicating the intelligence engine.

## Main bootstrap reduction
- V75 `app/main.py`: 1995 lines
- V76 `app/main.py`: 1466 lines
- Reduction in this release: 529 lines (~26.5%)

`main.py` is now primarily application bootstrap/middleware/router registration plus the remaining domains that have not yet been extracted.

## Compatibility and security
- No intended public URL changes.
- Server-side role checks and CSRF checks remain in the extracted write routes.
- Media/Cloudflare upload, protected assets, video watermarking, auth and learning-runtime modules were not weakened or reimplemented.
- No duplicate HTTP method/path pairs were detected by the V76 architecture test.

## Validation completed
- `AUTH HTTP CONTRACT V53 OK`
- `V68 AUTH ROUTER + SERVICE EXTRACTION: PASS`
- `MEDIA STRUCTURE HARDENING OK`
- `V57 RESUMABLE LECTURE + ATTACHMENT UPLOAD FLOW OK`
- `NAVIGATION CONTRACT OK`
- `HOMEPAGE FEATURES V51 FLOW OK`
- `CONTENT CENTER V22 FLOW OK`
- `CONTENT SCHEDULING V24 FLOW OK`
- `REVISION PLAN V27 FLOW OK`
- `LEARNING INTELLIGENCE V29 FLOW OK`
- `SMART TUTOR V30 FLOW OK`
- `ADMIN DOMAINS V74 OK`
- `COMMUNITY DOMAINS V75 OK`
- `V72 LEARNING RUNTIME FULL DECOUPLING: PASS`
- `PROTECTED ASSETS V37 FLOW OK`
- `VIDEO WATERMARK V39 FLOW OK`
- `V76 ARCHITECTURE CLEANUP: PASS`
- Python compile/compileall: PASS

## Test-run note
A few long combined shell test batches reached their command timeout after earlier tests had already passed. The remaining tests were then executed individually/in smaller batches and passed. This is a test-runner duration issue, not a failing assertion.

## Remaining work after V76
The largest remaining responsibilities in `main.py` are teacher/admin dashboard aggregation, quiz/question-bank authoring, homework administration, push notifications, activation-code inventory, profile/search/student utilities, English tools, system status and certificates. These should be extracted in later releases rather than moved all at once.

## Production acceptance still required
Local tests cannot prove live third-party connectivity. After deployment, run production acceptance against the real Cloudflare Stream/R2, Paymob, and messaging/OTP secrets and domains.
