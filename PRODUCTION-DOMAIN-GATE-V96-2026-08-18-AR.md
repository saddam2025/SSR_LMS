# منصة المستشار — Production / Domain Gate V96

تاريخ المراجعة: 2026-08-18

## القرار
**GO للسورس والحزمة المحلية.** يبقى Production Acceptance على Railway/Cloudflare بالحسابات الحقيقية قبل فتح المنصة للطلاب.

## خط الأساس
- Master Source: Sherif Visual/System Parity Final V96.
- اختبارات التطبيق الكاملة قبل توحيد قوالب Production: **92/92 PASS**.
- لم يتم تغيير منطق التطبيق في هذه الجولة؛ التعديل محصور في اتساق قوالب ENV الخاصة بالنشر.

## تصحيحات Production في هذه الجولة
- توحيد `.env.example` و`.env.railway.example` و`CLOUDFLARE-PRODUCTION-ENV-TEMPLATE.env`.
- `STORAGE_PREFLIGHT_ROUNDTRIP=false` افتراضيًا حتى لا يمنع عطل R2 مؤقت ترقية نسخة ويب سليمة.
- `RUN_STARTUP_PREFLIGHT=false` على Railway لأن `app.deploy_prepare` يعمل كـ Pre-Deploy Command.
- توحيد HSTS defaults: includeSubDomains=false وpreload=false لحين اكتمال قبول جميع النطاقات الفرعية.
- توحيد Redis task worker: embedded / max attempts 3 / claim idle 60000ms.
- الحفاظ على `healthcheckPath=/ready` و`healthcheckTimeout=300`.

## تحقق بعد التعديل
- Regression الخاص بالنشر/الأمان/Parity: **21/21 PASS**.
- Jinja: **66 template PASS**.
- JavaScript: **15 file PASS**.
- Shell syntax: **14 script PASS**.
- JSON: **7 file PASS**.
- `railway.toml`: PASS.
- Static Release Check: PASS.
- Release Manifest: PASS — **387 file**.
- Release Candidate: PASS بعد تنظيف آثار الاختبارات المحلية.

## تشغيل حي محلي من نفس الشجرة
- `/health`: HTTP 200 — version V96.
- `/ready`: HTTP 200.
- `/`: HTTP 200.
- `/Login`: HTTP 200.
- `/english-lab`: HTTP 200.
- `/register`: HTTP 200.
- `/forgot-password`: HTTP 200.
- `/app-version.json`: HTTP 200.
- `/Courses`: HTTP 303 مقصود إلى `/#courses`.
- سجل التشغيل في هذا الفحص: لا توجد ERROR/Traceback/HTTP 5xx.

## ما لا يمكن إثباته محليًا
لا يمكن إعلان PASS نهائي للخدمات التالية قبل ربط الحسابات الحقيقية:
- Railway PostgreSQL.
- Railway Redis.
- Cloudflare R2.
- Cloudflare Stream.
- Paymob إن تم تفعيله.
- DNS/TLS للدومين النهائي.

## Acceptance بعد النشر
1. Pre-Deploy يطبع `MOSTASHAR DEPLOY PREPARE OK`.
2. Deployment يصبح Active.
3. `/health` و`/ready` = 200.
4. Admin login + MFA.
5. Student login بالبريد/الهاتف وParent login.
6. إنشاء كورس ودرس.
7. رفع PDF/صورة على R2 وفتحهما كطالب مصرح.
8. رفع فيديو Stream عبر TUS وتشغيله لطالب مشترك فقط.
9. اختبار Quiz / Assignment / Support / Smart Tutor.
10. اختبار Paymob في Test Mode قبل الإنتاج الحقيقي.
11. إضافة الدومين في Railway ثم نسخ سجلات DNS التي يصدرها Railway إلى Cloudflare حرفيًا.
12. التحقق من SSL وwww/root والـredirects ثم مراقبة Logs/CPU/RAM/DB connections.
