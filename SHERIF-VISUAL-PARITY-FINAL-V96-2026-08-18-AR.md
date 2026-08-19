# منصة المستشار — Sherif Visual/System Parity Final V96

تاريخ المراجعة: 2026-08-18
Release marker: `V96-SHERIF-VISUAL-PARITY-20260818-04`

## الهدف
استكمال محاكاة نمط تجربة الاستخدام والوظائف العامة المنشورة في منصة شريف المصري، مع الحفاظ الكامل على هوية المستشار رجب صديق وكود المنصة ووظائف الـLMS الأصلية. لا يتضمن هذا العمل نسخ Backend أو سورس خاص غير منشور لأي منصة أخرى.

## ما تم استكماله في هذه المرحلة
- تنظيم قسم التعلم العام إلى مجموعتين واضحتين: **أفكار ذهبية ومنظمة** و**مراجعات دائمة ومستمرة**.
- تثبيت استراتيجيات: خريطة ذهنية يومية، روتين 10-20-30، التعلم بالنطق المباشر، بطاقات مراجعة مرئية، مراجعة متباعدة، التحدي الثنائي الصوتي، جدول المراجعة الأسبوعي، مراجعة الصدى الصوتي، الصناديق الذكية، تحدي الدقيقة، والقاموس الناطق الذهبي.
- القاموس الناطق يدعم US/UK ويحتوي كلمات مقترحة: Hello, Beautiful, Amazing, Study, Review, Pronunciation, Modern, Simple, Focus, Success.
- الإبقاء على بوابة Vocabulary / Tenses / Grammar / Speaking ومختبر الإنجليزية الكامل.
- الإبقاء على آراء الطلاب المرتبطة بقاعدة البيانات والإدارة من Admin.
- تحسين فلاتر الكورسات على الموبايل: جميع الفلاتر تلتف داخل عرض الشاشة بدل وضع أزرار قابلة للضغط خارج الـviewport.
- تحديث fingerprint/cache-busting وrelease header إلى الإصدار الحالي.

## QA البرمجي
- اختبارات V96: **66/66 PASS**.
- بقية اختبارات pytest: **26/26 PASS**.
- الإجمالي: **92/92 PASS**.
- Python compile (`app`, `deploy`): PASS.
- Jinja templates: **66** قالب PASS.
- JavaScript syntax: **11** ملف PASS.
- Shell syntax: **14** سكربت PASS.
- JSON parse: **7** ملفات PASS.
- Route inventory: **240** route.
- Database metadata: **77** table.
- Template inventory: **387** link + **193** button + **139** form.

## Live HTTP verification
تم تشغيل Uvicorn بقاعدة SQLite معزولة خارج شجرة السورس والتحقق من:
- `/` = 200.
- `/health` = 200.
- `/Login` = 200.
- `/Courses` = 200 ثم anchor الكورسات.
- `/english-lab` = 200.
- Student phone login (`01000000001`) = 303 إلى `/dashboard` في بيئة الاختبار المحلية.
- `/dashboard`, `/study-plan`, `/smart-tutor`, `/english-tools` = 200 بعد الدخول.
- جميع روابط الصفحة الرئيسية الداخلية التي تم اكتشافها: لا 404 ولا 5xx، والـanchors موجودة.

## Visual / interaction QA
تم Render للـHTML الحي مع نفس CSS والصور المحلية في Chromium Headless على:
- Desktop: **1536×1024** — document width = viewport width، 0 actionable elements خارج الشاشة، 0 actionable overlaps.
- Tablet: **1024×768** — document width = viewport width، 0 actionable elements خارج الشاشة، 0 actionable overlaps.
- Android: **390×844** — document width = viewport width، 0 actionable elements خارج الشاشة، 0 actionable overlaps.
- Mobile menu: مغلق = panel غير قابل للتفاعل؛ مفتوح = panel ظاهر ويعمل.
- Course filters على Android: جميعها داخل الشاشة، وتم اختبار فلترة First/Third حيًا في JavaScript.
- Dictionary suggestion click: تحديث input إلى `Pronunciation` نجح.

## ملاحظة المتصفح
سياسة بيئة الأدوات تمنع Chromium من التنقل مباشرة إلى `localhost`، لذلك تم جلب HTML من Uvicorn فعليًا ثم Render نفس HTML/CSS/images داخل Chromium عبر `set_content`. فحوص HTTP والجلسات والدخول تمت مباشرة على Uvicorn الحقيقي.

## قرار المرحلة
**PASS — النسخة جاهزة كـMaster Source أحدث للمستشار قبل Production Acceptance على Railway/Cloudflare بالحسابات الحقيقية.**
