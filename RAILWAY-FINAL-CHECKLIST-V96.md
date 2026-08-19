# Railway Final Checklist — V96 Critical Hardened

## Source / GitHub
- [ ] GitHub يحتوي **نفس release ZIP/source** وليس نسخة أقدم.
- [ ] `railway.toml`, `Dockerfile`, `container-start.sh` موجودة في root.
- [ ] لا توجد `.env` حقيقية أو SQLite DB أو private keys في المستودع.

## Railway core
- [ ] Web + PostgreSQL + Redis في المشروع.
- [ ] `ENV=production`.
- [ ] `PUBLIC_BASE_URL=https://ragab-seddik.com`.
- [ ] `DATABASE_URL` مربوط بخدمة PostgreSQL من Railway UI.
- [ ] `REDIS_URL` مربوط بخدمة Redis من Railway UI.
- [ ] `APP_SECRET` عشوائي 64+ حرفًا.
- [ ] `ADMIN_EMAIL` + كلمة مرور Admin قوية.
- [ ] `REQUIRE_STAFF_MFA=true`.
- [ ] `RUN_SEED_ON_START=false`.
- [ ] `RUN_STARTUP_PREFLIGHT=false`.
- [ ] `SEPARATED_FRONTEND_ENABLED=false`.
- [ ] لا يوجد PORT ثابت في Variables.
- [ ] Pre-Deploy = `python -m app.deploy_prepare` (من `railway.toml`).
- [ ] Healthcheck path = `/ready` وtimeout = 300 (من `railway.toml`).

## Runtime / scale
- [ ] `WEB_CONCURRENCY=2` كبداية.
- [ ] `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`.
- [ ] `TASK_WORKER_MODE=embedded`, مع Redis متاح.
- [ ] `WATERMARK_MAX_CONCURRENT=2`.

## R2 / uploads
- [ ] R2 endpoint/bucket/access/secret صحيحة.
- [ ] `DIRECT_R2_UPLOAD_ENABLED=true`.
- [ ] CORS من `R2-CORS-POLICY-V96.json` مطبق.
- [ ] `STORAGE_PREFLIGHT_ROUNDTRIP=false` للإطلاق المرن، ثم اختبار R2 الحقيقي بعد Active.
- [ ] PDF وصورة يُرفعان ويفتحان بحساب طالب مصرح له.

## Stream / content protection
- [ ] Stream credentials + edge signing secret موجودة.
- [ ] Stream Edge Worker منشور.
- [ ] `ALLOW_DIRECT_VIDEO_PROXY=false`.
- [ ] فيديو TUS يُرفع ويُستكمل بعد انقطاع تجريبي.
- [ ] الفيديو لا يعمل لحساب غير مشترك.

## Live acceptance
- [ ] Pre-Deploy ينجح ويطبع `MOSTASHAR DEPLOY PREPARE OK`.
- [ ] Deployment يصبح Active.
- [ ] `/health` = 200.
- [ ] `/ready` = 200.
- [ ] Admin / Student email+phone / Parent login works.
- [ ] Quiz auto-grading + attempt limits works.
- [ ] Community WhatsApp groups الأربعة صحيحة.
- [ ] لا توجد 5xx في Railway logs أثناء acceptance.
- [ ] راقب CPU/RAM/DB connections قبل فتح المنصة لعدد كبير من الطلاب.
