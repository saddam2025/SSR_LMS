# Ragab Seddik LMS — Production Security Core

منصة تعليمية Full-Stack مبنية بـ FastAPI + SQLAlchemy، مع نسخة تطوير سريعة على SQLite وبنية Production تعتمد PostgreSQL + Redis + Nginx عبر Docker Compose.

## الموجود فعليًا في هذه النسخة

- منصة مدرس واحد لمستر رجب صديق: لا يوجد نظام تعدد مدرسين.
- أدوار التشغيل: Super Admin / Admin / Content Manager / Support / Accounting / Student / Parent.
- كورسات، دروس، تسجيلات Enrollments، اختبارات وتصحيح تلقائي.
- حد أقصى لمحاولات الاختبار مع إمكانية خلط الأسئلة.
- تتبع تقدم الدروس.
- اشتراكات وقاعدة بيانات لكوبونات الخصم (نواة قابلة لربط بوابة دفع).
- Argon2 لكلمات المرور.
- CSRF + Security Headers + CSP + HSTS في Production.
- Rate limiting لمحاولات الدخول: Redis عند توفره، مع fallback محلي للتطوير.
- قفل مؤقت للحساب بعد محاولات فاشلة متكررة.
- Server-side revocable sessions: الكوكي لا تحمل user id؛ تحمل token عشوائيًا فقط، والسيرفر يحتفظ بالـhash.
- Idle timeout + absolute session timeout.
- Device registration + حد أقصى للأجهزة للطالب.
- مركز أمان Admin لحظر جهاز أو إنهاء جلسة فورًا.
- Audit log للأحداث الأمنية المهمة.
- Signed short-lived protected-content token مربوط بالطالب والجلسة.
- Dynamic/tiled watermark على صفحة المحتوى مرتبطة بالطالب.
- وسائل browser deterrence للطباعة/النسخ وبعض الاختصارات.
- Docker Compose: PostgreSQL + Redis + Web + Nginx مع healthchecks.

## تشغيل سريع محليًا

### Windows
شغّل `start.bat` ثم افتح:
`http://127.0.0.1:8000`

### Linux/macOS
```bash
chmod +x start.sh
./start.sh
```

## الحسابات التجريبية

- Admin محلي: `admin@ragab-seddik.local` / `ChangeMe123!`
- Student محلي: `student@ragab-seddik.local` / `Student123!`
- Parent محلي: `parent@ragab-seddik.local` / `Parent12345!`

هذه الحسابات للتطوير المحلي فقط. في Production يجب تعيين `ADMIN_EMAIL` و`ADMIN_PASSWORD` كأسرار وعدم استخدام كلمات المرور التجريبية.

يجب تغيير جميع كلمات المرور التجريبية قبل أي نشر حقيقي.

## تشغيل Production عبر Docker

1. انسخ `.env.example` إلى `.env`.
2. ضع `APP_SECRET` عشوائيًا بطول كبير، وغير كلمة مرور PostgreSQL.
3. شغّل `docker compose up --build -d`.
4. افتح `http://localhost:8080` للتجربة خلف Nginx.
5. عند الربط بدومين حقيقي، يجب وضع TLS/HTTPS أمام Nginx أو تهيئة شهادة مباشرة.

## ملاحظة DRM / تصوير الشاشة

المنصة تطبق watermark وردعًا داخل المتصفح، لكنها **لا تدّعي** منع Screenshot/Screen Recording بنسبة 100%. حماية الفيديو الأعلى تتطلب مزود DRM/License Server فعلي (Widevine/FairPlay/PlayReady) وبيانات اعتماد المزود. بنية التوكنات القصيرة الحالية مصممة لتكون نقطة الربط مع طبقة DRM/CDN لاحقًا بدون كشف روابط الملفات الخام للطالب.

## الاختبارات

```bash
PYTHONPATH=. python tests/smoke_test.py
```

ثم يمكن التحقق من `/health`.

## قبل الإطلاق التجاري

- تغيير الأسرار وكلمات المرور الافتراضية.
- ربط PostgreSQL/Redis بخدمات خاصة غير مكشوفة للإنترنت.
- HTTPS فقط.
- نسخ احتياطي مشفر واختبار الاستعادة.
- ربط مزود دفع حقيقي عبر webhooks موقعة.
- ربط Object Storage/CDN خاص للمحتوى بدل URLs مباشرة.
- DRM حقيقي للفيديو إذا كان شرطًا تجاريًا.
- فحص Dependency/SAST/DAST واختبار اختراق قبل الإطلاق.


## Commercial modules (2026)
- Paymob Intention API / Unified Checkout integration (credentials required for live transactions).
- HMAC-SHA512 webhook verification + amount/currency reconciliation before enrollment activation.
- Coupons, redemptions, payment ledger, subscriptions and student notifications.
- Private lesson assets with local or S3-compatible storage and short-lived presigned access.
- Protected upload validation (allowlist + file signature + size limit).
- DRM-provider-ready environment hooks; live Widevine/FairPlay/PlayReady requires vendor credentials/license infrastructure.

## Final 2026 additions
- Parent role + parent dashboard.
- Parent-to-student linking from Admin.
- Parent academic analytics: enrollments, completed lessons, watch time, quiz averages and homework status.
- Server-enforced sequential lesson unlocking.
- Homework creation, student submission, teacher grading and feedback.
- Student notification after homework grading.
- Course learning path now presents lessons, homework and quizzes in one flow.
- Demo parent: `parent@ragab-seddik.local` / `Parent12345!`

## Current verified release
V96 Critical Hardened is the current Railway release candidate. The normal production topology is single-domain, Railway preparation runs in Pre-Deploy, `/ready` is the deep deployment healthcheck, large admin lists are paginated/set-based, background communications use reliable Redis Streams, and protected-media watermark work is concurrency-bounded.

### Production login bootstrap
- Keep `RUN_SEED_ON_START=false`.
- Set real `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` in Railway Variables before the first deploy.
- On a fresh production database the startup creates **only** the initial Admin account; it never seeds demo students/content and never overwrites an existing Admin password on restart.
- With `REQUIRE_STAFF_MFA=true`, the first Admin login goes directly to `/account/security?required=1` to enroll MFA.
- Keep `SEPARATED_FRONTEND_ENABLED=false` unless a separate student frontend has actually been deployed and accepted.

See `RAILWAY-DEPLOYMENT-V96-AR.md` and `RAILWAY-FINAL-CHECKLIST-V96.md` for the current deployment order and acceptance steps.

## Firebase Cloud Messaging
Firebase push is configured through `FCM_ENABLED`, `FIREBASE_PROJECT_ID`, and `FIREBASE_SERVICE_ACCOUNT_JSON`. Keep service-account credentials in Railway/environment secrets only; they are intentionally not included in this source archive.


## V96 Wheel & Typography Refresh — 2026-08-18

- Native responsive English Skills wheel replaces the old image-hotspot wheel.
- Arabic UI typography: Tajawal body + Cairo headings; English labels: Montserrat.
- Cache/PWA release fingerprint: `V96-WHEEL-TYPOGRAPHY-REFRESH-20260818-01`.
- Full regression suite: 95 tests passing before packaging.
- See `FINAL-QA-WHEEL-TYPOGRAPHY-V96-2026-08-18-AR.md` for verification details.
