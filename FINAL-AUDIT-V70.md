# Mostashar V70 — Student Learning Runtime Router

## Scope
V70 extracts the authenticated student learning runtime HTTP routes from `app/main.py` into `app/routers/learning_runtime.py` while preserving the existing public URLs and authorization behavior.

Moved runtime routes include course view, lesson playback, lesson assistant, checkpoints, discussions, homework view/submission, quiz view/submission, lesson progress, protected lesson/video authorization, and mobile offline DRM capability/grant.

## Architecture
- `app/main.py`: 3380 -> ~3070 lines (bootstrap/shared helpers remain temporarily).
- New `app/routers/learning_runtime.py` owns the student runtime routes.
- No duplicate HTTP route registrations were found.
- V70 keeps a documented transitional compatibility bridge to shared helper implementations in `app.main`; future releases can move those helpers into domain services without changing URLs.

## Security regression fixed during V70
The V69 course service extraction used the environment variable directly for its production check, while legacy security tooling can toggle `main.IS_PRODUCTION`. V70 restores the runtime production guard in `main.validated_video_url`, preventing raw MP4/WebM links when direct proxying is disabled.

## Verification
Passed locally:
- V70 Student Learning Runtime Router
- Auth HTTP Contract V53
- Media Integrity V56
- Resumable Lecture Upload V57
- Separated Student V60
- Separated Lesson V61
- Separated Interactions V62
- Separated Learning V63
- Request Context V66
- Media/Commerce Router V67
- Auth Router V68
- Courses/Lessons Router V69
- Navigation Contract
- Protected Assets V37
- Video Watermark V39
- Commerce Center V14
- Final End-to-End Flow
- Python compileall

Production-only integrations (Cloudflare Stream/R2, Paymob, SMS/OTP and real DRM provider) still require acceptance tests with production credentials after deployment.
