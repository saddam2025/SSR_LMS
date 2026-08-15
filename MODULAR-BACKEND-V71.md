# V71 Modular Backend — Learning Runtime Services

V71 removes the broad `app.main` compatibility bridge from `app/routers/learning_runtime.py`.

## New service
`app/services/learning_runtime.py` now owns application-module-independent learning runtime domain helpers:
- course authorization / schedule / lesson unlock access (re-exported from `app.access`)
- idempotent point awards
- course completion calculation
- certificate issuance
- direct-video proxy production policy
- Range header validation
- production-safe direct video URL validation

## Router dependencies
The learning runtime router now imports DB, models, request context, security and service dependencies directly. The former dozens of `getattr(_legacy, ...)` bindings are removed.

## Transitional compatibility still present
Three narrow bootstrap dependencies remain intentionally:
1. legacy HTML `render_template`
2. legacy `_render_lesson_page`
3. legacy `_smart_study_answer`

`main.IS_PRODUCTION` is also passed into playback policy wrappers temporarily to preserve existing security-test and migration semantics.

## Bootstrap reduction
`app/main.py` was reduced from about 3070 lines in V70 to about 3016 lines in V71. Completion, certificate, points and playback validation implementations in `main.py` are now thin wrappers over the service.
