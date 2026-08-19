# Mostashar Stream Edge Worker

هذا الـWorker جزء إلزامي من حماية فيديوهات Cloudflare Stream في وضع Production.
التطبيق على Railway لا يعرض Stream UID كمسار تشغيل مباشر. بدلًا من ذلك يصدر grant قصير العمر وموقّع HMAC على المسار:

`/_edge/stream/<VIDEO_UID>?grant=...`

الـWorker يتحقق من التوقيع، تطابق UID، انتهاء الصلاحية (بحد أقصى 300 ثانية)، ثم يستخدم Stream Binding لإنشاء signed playback token ويحوّل الـiframe إلى Cloudflare Stream.

## النشر

1. انسخ `wrangler.toml.example` إلى `wrangler.toml` وعدّل الدومين و`CF_STREAM_CUSTOMER_CODE` فقط عند الحاجة.
2. من مجلد `cloudflare/stream-edge` شغّل Wrangler المناسب لحسابك.
3. أضف السر بنفس قيمة Railway `CF_EDGE_SIGNING_SECRET`، ولا تضع السر داخل Git أو ZIP إعدادات عامة:
   `npx wrangler secret put CF_EDGE_SIGNING_SECRET`
4. انشر الـWorker وتأكد أن Route يغطي `ragab-seddik.com/_edge/stream/*` (وwww إذا كنت تستخدمه).
5. أبقِ Stream Binding باسم `STREAM` كما هو في الملف.

## قبول سريع بعد النشر

- فتح رابط `/_edge/stream/<uid>` بدون grant يجب أن يعيد 403.
- grant محرّف أو منتهي يجب أن يعيد 403.
- grant صادر من درس مصرح للطالب به يجب أن يعيد 302 إلى `customer-...cloudflarestream.com/<SIGNED_TOKEN>/iframe`.
- فيديو Stream نفسه يجب أن يكون `requireSignedURLs=true`، وAllowed Origins يجب أن تقتصر على دومينات المنصة.
