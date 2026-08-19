# بيانات نشر منصة المستشار V96

## الدومين
- Primary: `https://ragab-seddik.com`
- WWW: `https://www.ragab-seddik.com`
- `PUBLIC_BASE_URL=https://ragab-seddik.com`
- `ALLOWED_HOSTS=ragab-seddik.com,www.ragab-seddik.com,healthcheck.railway.app`

## Railway Services المطلوبة
- Web service من هذا السورس باستخدام Dockerfile.
- PostgreSQL service.
- Redis service.

## Core Variables المطلوبة قبل أول Deploy
- `ENV=production`
- `APP_SECRET`: عشوائي 64+ حرفًا.
- `PUBLIC_BASE_URL=https://ragab-seddik.com`
- `ALLOWED_HOSTS=ragab-seddik.com,www.ragab-seddik.com,healthcheck.railway.app`
- `DATABASE_URL=${{Postgres.DATABASE_URL}}`
- `REDIS_URL=${{Redis.REDIS_URL}}`
- `ADMIN_NAME=مدير منصة المستشار`
- `ADMIN_EMAIL`: بريد الإدارة الحقيقي.
- `ADMIN_PASSWORD`: كلمة مرور قوية 14+ حرفًا وغير مستخدمة في مكان آخر.
- `REQUIRE_STAFF_MFA=true`

## Cloudflare Stream
- `CLOUDFLARE_DEPLOYMENT=true`
- `CF_EDGE_SIGNING_SECRET`: سر مختلف 32+ حرفًا.
- `CF_ACCOUNT_ID`
- `CF_STREAM_API_TOKEN`
- `CF_STREAM_CUSTOMER_CODE`
- `VIDEO_ALLOWED_HOSTS=cloudflarestream.com,videodelivery.net`
- `ALLOW_DIRECT_VIDEO_PROXY=false`
- `STREAM_ALLOWED_ORIGINS=ragab-seddik.com,www.ragab-seddik.com`

## Cloudflare R2
- `STORAGE_BACKEND=s3`
- `S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com`
- `S3_REGION=auto`
- `S3_BUCKET=<PRIVATE_BUCKET>`
- `S3_ACCESS_KEY_ID=<R2_ACCESS_KEY>`
- `S3_SECRET_ACCESS_KEY=<R2_SECRET_KEY>`
- `DIRECT_R2_UPLOAD_ENABLED=true`
- طبّق `R2-CORS-POLICY-V96.json` على الـBucket.

## Runtime defaults المعتمدة
- `RUN_SEED_ON_START=false`
- `RUN_STARTUP_PREFLIGHT=false`
- `STORAGE_PREFLIGHT_ROUNDTRIP=false`
- `WEB_CONCURRENCY=2`
- `DB_POOL_SIZE=5`
- `DB_MAX_OVERFLOW=5`
- `TASK_WORKER_MODE=embedded`
- `TASK_MAX_ATTEMPTS=3`
- `TASK_CLAIM_IDLE_MS=60000`
- `HSTS_INCLUDE_SUBDOMAINS=false`
- `HSTS_PRELOAD=false`

## Paymob — لا تفعله قبل Test Acceptance
- `PAYMOB_SECRET_KEY`
- `PAYMOB_PUBLIC_KEY`
- `PAYMOB_HMAC_SECRET`
- `PAYMOB_INTEGRATION_ID`

## إنشاء أسرار قوية محليًا
استخدم مدير أسرار موثوقًا أو الأمر التالي محليًا، ولا تحفظ الناتج داخل Git:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

ولكلمة مرور الإدارة استخدم Password Manager لتوليد كلمة مرور فريدة لا تقل عن 20 حرفًا.

## ملفات مرجعية داخل الحزمة
- `.env.railway.example` — القالب الأساسي لـRailway.
- `CLOUDFLARE-PRODUCTION-ENV-TEMPLATE.env` — قالب Cloudflare/R2/Stream المتوافق.
- `R2-CORS-POLICY-V96.json` — سياسة CORS.
- `RAILWAY-DEPLOYMENT-V96-AR.md` — خطوات النشر.
- `RAILWAY-FINAL-CHECKLIST-V96.md` — Acceptance checklist.
- `PRODUCTION-DOMAIN-GATE-V96-2026-08-18-AR.md` — نتيجة آخر Gate.

## ملاحظة أمنية
لا توجد بيانات Production حقيقية أو مفاتيح حسابات داخل السورس. القيم الحقيقية يجب إدخالها كـRailway Variables / Cloudflare Secrets فقط.
