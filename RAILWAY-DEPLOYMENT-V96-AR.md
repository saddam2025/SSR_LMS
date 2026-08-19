# دليل نشر Mostashar V96 Critical Hardened على Railway

## المعمارية المعتمدة
النشر الافتراضي **دومين واحد**: `https://ragab-seddik.com`.
لا تستخدم `api.ragab-seddik.com` أو `student.ragab-seddik.com` إلا إذا قررت لاحقًا تشغيل Frontend منفصل وضبط `SEPARATED_FRONTEND_ENABLED=true` بعد اختباره.

## 1) خدمات Railway
أنشئ Web + PostgreSQL + Redis داخل نفس المشروع. اربط Web بمستودع GitHub الذي يحتوي نفس إصدار السورس الذي تم اختباره.

## 2) ما يقرأه Railway من السورس
`railway.toml` يحدد:
- Dockerfile build.
- Pre-Deploy: `python -m app.deploy_prepare`.
- Healthcheck: `/ready`.
- Healthcheck timeout: 300 ثانية.

Pre-Deploy يفحص Production Variables، ينتظر PostgreSQL/Redis، يجهز الـschema/indexes، ثم ينشئ أول Admin بشكل idempotent. لذلك أي خطأ DB/Redis/Variables يظهر قبل مرحلة Network Healthcheck.

## 3) Variables الأساسية
استخدم `.env.railway.example` كقائمة أسماء فقط، واستبدل كل `REPLACE_...` بقيم حقيقية داخل Railway Variables.
أهم القيم: `ENV=production`, `PUBLIC_BASE_URL=https://ragab-seddik.com`, `APP_SECRET` قوي، `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `REQUIRE_STAFF_MFA=true`, `RUN_SEED_ON_START=false`, `RUN_STARTUP_PREFLIGHT=false`, `SEPARATED_FRONTEND_ENABLED=false`.

استخدم Railway Variables UI لربط `DATABASE_URL` و`REDIS_URL` بالخدمتين؛ لا تخمن اسم reference variable إذا كان Railway يعرض اسمًا مختلفًا.

**لا تضف PORT يدويًا.** Railway يحقنه، والتطبيق يستمع على `0.0.0.0:$PORT`.

## 4) Healthcheck
- Railway: `/ready`.
- `/ready` يجب أن يرجع 200 فقط عندما PostgreSQL وRedis جاهزان.
- `/health` فحص خفيف لتشخيص أن عملية الويب نفسها تعمل.
- `healthcheck.railway.app` مسموح به داخل TrustedHost تلقائيًا.

## 5) إعداد أولي للحمل
ابدأ بـ `WEB_CONCURRENCY=2`, `DB_POOL_SIZE=5`, `DB_MAX_OVERFLOW=5`, `UVICORN_BACKLOG=2048`، ثم زِد السعة بناءً على Railway metrics وحدود اتصالات PostgreSQL، وليس بالتخمين.

المهام الخلفية تستخدم Redis Streams مع ACK/retry/reclaim. الإعداد الافتراضي `TASK_WORKER_MODE=embedded`; يمكن فصل Worker لاحقًا إذا أصبح حجم الرسائل كبيرًا.

## 6) R2 ورفع PDF/الصور
اضبط `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `DIRECT_R2_UPLOAD_ENABLED=true`.
طبّق `R2-CORS-POLICY-V96.json` على الـBucket.
الإعداد الموصى به للنشر `STORAGE_PREFLIGHT_ROUNDTRIP=false`; اختبر Put/Get/Delete ورفع ملف حقيقي بعد أن يصبح Deployment Active. اجعله `true` فقط إذا أردت أن أي عطل R2 مؤقت يمنع النشر بالكامل.

## 7) Cloudflare Stream
اضبط بيانات Stream، انشر Worker الموجود في `cloudflare/stream-edge/`، واترك `ALLOW_DIRECT_VIDEO_PROXY=false`. اختبر رفع TUS قابل للاستكمال وتشغيل الفيديو بحساب طالب مشترك.

## 8) حماية الملفات والذاكرة
الملفات المحمية عليها watermark ديناميكي. الإعداد الافتراضي `WATERMARK_MAX_CONCURRENT=2` لكل Web worker لمنع ضغط PDF/الصور الكبير من إسقاط الـinstance بسبب الذاكرة.

## 9) بعد أول Deploy
تحقق من `/health` و`/ready`، ثم Admin MFA، تسجيل دخول Admin/Student/Parent، الجروبات الأربعة، رفع PDF/صورة، Stream video، التصحيح الآلي، الصلاحيات، Logout، وراقب Railway logs/CPU/RAM/DB connections أثناء اختبار متزامن محدود.
