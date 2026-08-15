# FINAL AUDIT — V91 Railway Upload Preflight Hardening

## الهدف
معالجة سيناريو خطأ رفع الدرس/المرفقات على Railway ومنع بدء الخادم بإعداد R2 ناقص.

## الإصلاحات
- V90: رسائل 500 أوضح مع Request ID، rollback عند فشل إنشاء الدرس، وتحويل نقص VIDEO_ALLOWED_HOSTS إلى 503 واضح.
- V91: عند CLOUDFLARE_DEPLOYMENT=true أصبح R2 مطلوبًا بالكامل في Production Preflight: endpoint + bucket + access key + secret key.
- إذا كان إعداد R2 ناقصًا، يفشل الـDeploy/Preflight من البداية بدل ظهور الخطأ أثناء رفع الدرس.
- اختبار V57 يستخدم مجلد /tmp فريدًا لكل process لمنع تلوث الاختبار بمجلد قديم غير قابل للكتابة.

## التحقق
- PASS: V91/V90 focused tests (4 tests)
- PASS: Auth HTTP Contract V53
- PASS: Media Integrity V56
- PASS: Resumable Lecture Upload V57
- PASS: Production Release Gate
- PASS: Python compile

## أهم إعدادات Railway المطلوبة
- ENV=production
- CLOUDFLARE_DEPLOYMENT=true
- VIDEO_ALLOWED_HOSTS=cloudflarestream.com,videodelivery.net
- STORAGE_BACKEND=s3
- S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
- S3_BUCKET=<PRIVATE_BUCKET>
- S3_ACCESS_KEY_ID=<SECRET>
- S3_SECRET_ACCESS_KEY=<SECRET>
- CF_ACCOUNT_ID=<ACCOUNT_ID>
- CF_STREAM_API_TOKEN=<STREAM_EDIT_TOKEN>
- CF_EDGE_SIGNING_SECRET=<32+ RANDOM CHARS>
