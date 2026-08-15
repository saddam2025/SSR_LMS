# إصلاح وتشخيص خطأ رفع الدرس — V90

## ما تم إصلاحه
- غياب `VIDEO_ALLOWED_HOSTS` لم يعد يظهر كـ HTTP 500؛ أصبح 503 برسالة إعداد واضحة.
- إنشاء الدرس أصبح Transaction واحدة تشمل Audit Log، مع `rollback()` عند الفشل.
- أي 500 غير متوقع يعرض `Request ID` يمكن البحث عنه في Railway Logs.
- أخطاء R2 وCloudflare Stream تبقى برسائل مخصصة (502/503) بدل الرسالة العامة.

## إعدادات إلزامية لرفع الفيديو على Railway
```text
ENV=production
CLOUDFLARE_DEPLOYMENT=true
VIDEO_ALLOWED_HOSTS=cloudflarestream.com,videodelivery.net
ALLOW_DIRECT_VIDEO_PROXY=false
CF_ACCOUNT_ID=<Cloudflare account id>
CF_STREAM_API_TOKEN=<Stream Edit token>
CF_EDGE_SIGNING_SECRET=<32+ random chars>
```

## إعدادات R2 للمرفقات
```text
STORAGE_BACKEND=s3
S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
S3_REGION=auto
S3_BUCKET=<private bucket>
S3_ACCESS_KEY_ID=<secret>
S3_SECRET_ACCESS_KEY=<secret>
```

## إذا ظهر 500
انسخ `Request ID` الظاهر في صفحة الخطأ وابحث عنه في Railway > Service > Logs.
السطر السابق له مباشرة سيحتوي Exception الفعلي بدون كشفه للطالب.

## ملاحظة اختبار V57
تم جعل مجلد الوسائط المؤقت للاختبار فريدًا لكل Process (`/tmp/mostashar-v57-media-<pid>`) حتى لا تفشل الاختبارات بسبب ملكية مجلد `/tmp` قديم. هذا تعديل Test Harness فقط ولا يغير مسار R2 في Production.

## V91 — منع فشل R2 أثناء الاستخدام
تم تشديد `Production Preflight`: عند `CLOUDFLARE_DEPLOYMENT=true` لن يعتبر R2 جاهزًا إلا بوجود:
- `S3_ENDPOINT_URL`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

إذا أي قيمة ناقصة، يفشل Deploy/Preflight بدل أن يبدأ الخادم ثم يفشل عند رفع المرفق.
