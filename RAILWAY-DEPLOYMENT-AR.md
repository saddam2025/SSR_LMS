# منصة المستشار V89 — جاهزة للنشر على Railway

## البنية المقترحة
- Railway Web Service: FastAPI Backend (هذا السورس).
- Railway PostgreSQL: قاعدة البيانات الرئيسية.
- Railway Redis: الجلسات/الكاش/الوظائف المرتبطة بـRedis.
- Cloudflare Pages: واجهة الطالب المنفصلة.
- Cloudflare Stream: فيديوهات المحاضرات.
- Cloudflare R2: ملفات PDF والصور والملفات المحمية.

## قبل النشر
1. ارفع هذا السورس إلى GitHub أو اربطه مباشرة بمشروع Railway.
2. أنشئ PostgreSQL وRedis داخل نفس مشروع Railway.
3. اربط DATABASE_URL وREDIS_URL كـReference Variables باستخدام Railway UI autocomplete.
4. انسخ أسماء المتغيرات من `.env.railway.example` إلى Variables في Railway، لكن لا ترفع الملف بقيم حقيقية إلى GitHub.
5. استخدم `ENV=production` حتى على Staging لكي تعمل Production Safety Gates.
6. اضبط Healthcheck على `/ready` (موجود في `railway.toml`).
7. يجب أن يتضمن `ALLOWED_HOSTS` القيمة `healthcheck.railway.app`، وأضف الدومين المؤقت الذي يولده Railway أثناء الاختبار إن استخدمته.

## أول اختبار
- GET /health => 200
- GET /ready => 200
- لا يوجد SQLite fallback في Production.
- PostgreSQL وRedis يعملان.
- RUN_SEED_ON_START=false.

## بعد نجاح Railway
اربط `api.ragab-seddik.com` بالـBackend ثم أكمل إعداد Cloudflare Stream وR2 وPages، وبعدها نفذ V82/V83/V84 قبل فتح المنصة للطلاب.
