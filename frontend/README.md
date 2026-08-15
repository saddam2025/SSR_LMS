# Mostashar V80 — Student Frontend on Cloudflare Pages

هذا المجلد هو واجهة الطالب المستقلة. في V80 أصبح النشر المقترح:

- Production student frontend: `https://student.ragab-seddik.com`
- Production backend/API: `https://api.ragab-seddik.com`
- Legacy/public fallback: `https://ragab-seddik.com` و `https://www.ragab-seddik.com`
- Staging student frontend: `https://staging-student.ragab-seddik.com`
- Staging backend/API: `https://staging-api.ragab-seddik.com`

## Cloudflare Pages

انشر مجلد `platform/frontend` كموقع Static. لا يوجد Build command إلزامي، والـOutput directory هو نفس المجلد عند Direct Upload، أو انسخه إلى مجلد build عند ربط Git.

`config.js` مضبوط للإنتاج على `https://api.ragab-seddik.com`. في Staging يجب استبداله أثناء الـbuild أو في نسخة staging إلى `https://staging-api.ragab-seddik.com`.

أضف Custom Domain `student.ragab-seddik.com` إلى مشروع Pages بعد نجاح Preview/Staging. ملفا `_headers` و`_redirects` موجودان داخل الـoutput ويُطبقان تلقائيًا في Pages.

## الجلسة والأمان

- الجلسة وCSRF يبقيان في Backend؛ لا توجد session tokens في `localStorage`.
- كل Fetch يستخدم `credentials: include`.
- Backend يسمح CORS فقط للأصول الموجودة في `FRONTEND_ORIGINS`.
- `student.ragab-seddik.com` و`api.ragab-seddik.com` تحت نفس site، بينما Cookies من نوع `__Host-` تبقى host-only على API.
- لا تغيّر `FRONTEND_PRIMARY_ORIGIN` إلى Pages preview domain في Production.
