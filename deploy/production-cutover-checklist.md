# V80 Production Cutover Checklist

## 1. Staging first
- Deploy backend with `cloudflare/wrangler.staging.jsonc` to `staging-api.ragab-seddik.com` using staging-only secrets.
- Deploy `platform/frontend` to a staging Pages project/custom domain `staging-student.ragab-seddik.com` with `API_BASE=https://staging-api.ragab-seddik.com`.
- Run `deploy/staging-acceptance.sh`.
- Upload a real test video through the lecture uploader, interrupt the connection, resume the same file, wait for Stream `ready`, then publish.
- Upload a PDF/image and verify protected access as enrolled student and 403 as unauthorized account.
- Run one Paymob sandbox/test transaction and confirm webhook idempotency and entitlement activation.
- Test staff MFA and student single-session behavior.

## 2. Data safety
- Take a fresh PostgreSQL backup with `ops/backup-postgres.sh`.
- Run `deploy/backup-restore-drill.sh` against a disposable database; never use the production database as the restore target.
- Verify R2 bucket scope is limited to the platform bucket and the token has only required object permissions.

## 3. Production secrets
Set secrets in Cloudflare, not Git/ZIP: APP_SECRET, CF_EDGE_SIGNING_SECRET, CF_ACCOUNT_ID, CF_STREAM_API_TOKEN, CF_STREAM_CUSTOMER_CODE, DATABASE_URL, REDIS_URL, ADMIN_EMAIL, ADMIN_PASSWORD, S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, and Paymob/FCM/SMS secrets when enabled.

## 4. Production domains
- Backend/API: `api.ragab-seddik.com`.
- Student Pages: `student.ragab-seddik.com`.
- Public/legacy fallback during migration: `ragab-seddik.com` and `www.ragab-seddik.com` remain attached to Backend until homepage/admin are fully migrated to a static/separate frontend.
- Do not remove the legacy fallback in the same release as the first Pages deployment.

## 5. Cutover acceptance
- `/health` returns 200 and `/ready` returns 200.
- CORS allows exactly `https://student.ragab-seddik.com` with credentials.
- Anonymous `/api/v1/session` returns 401.
- Student login redirects to `student.ragab-seddik.com/student/` and API calls carry the HttpOnly session.
- Video URLs are not exposed raw; Cloudflare grants/proxy paths remain short-lived.
- Paymob webhook signature verification works before enabling real payments.
- Monitor 5xx, login failures, Redis errors, DB pool timeouts, Stream upload failures and webhook failures after cutover.
