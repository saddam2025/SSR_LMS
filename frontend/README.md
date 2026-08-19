# Mostashar frontend

## Default production topology (V96)

The supported default is **single-domain**: `https://ragab-seddik.com`.
`config.js` therefore uses `window.location.origin` and does not require an API subdomain.

A separated student frontend is optional only when `SEPARATED_FRONTEND_ENABLED=true`; in that case generate environment-specific config with `deploy/build-pages.py` instead of using the default `config.js`.

أضف Custom Domain `student.ragab-seddik.com` إلى مشروع Pages بعد نجاح Preview/Staging. ملفا `_headers` و`_redirects` موجودان داخل الـoutput ويُطبقان تلقائيًا في Pages.

## الجلسة والأمان

- الجلسة وCSRF يبقيان في Backend؛ لا توجد session tokens في `localStorage`.
- كل Fetch يستخدم `credentials: include`.
- Backend يسمح CORS فقط للأصول الموجودة في `FRONTEND_ORIGINS`.
- `student.ragab-seddik.com` و`api.ragab-seddik.com` تحت نفس site، بينما Cookies من نوع `__Host-` تبقى host-only على API.
- لا تغيّر `FRONTEND_PRIMARY_ORIGIN` إلى Pages preview domain في Production.
