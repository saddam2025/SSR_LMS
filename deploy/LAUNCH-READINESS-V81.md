# V81 Launch Readiness Gate

V81 separates **code readiness** from **infrastructure acceptance**. A release is not launch-ready until all gates below pass.

## Gate A — local/repository
- `python release_check.py`
- `python tests/test_v81_launch_readiness.py`
- `python -m compileall -q app`
- `python deploy/validate-frontend-pages.py`
- From `cloudflare/`: `./preflight.sh` (runs `npm ci` and Wrangler/config checks).

## Gate B — secrets (never commit env files)
Create temporary local files outside Git for production and staging, then run:

```bash
python deploy/secret-readiness.py --production /secure/prod.env --staging /secure/stage.env
```

The command prints only missing key names/status, never secret values. Production and staging must use different `APP_SECRET`, edge signing secret, database URL, Redis URL, and admin password.

## Gate C — staging
- Deploy Worker/Container to `staging-api.ragab-seddik.com` using staging-only secrets.
- Deploy Pages to `staging-student.ragab-seddik.com`.
- Run `deploy/staging-acceptance.sh`.
- Real test: resumable Stream upload, protected PDF/image, staff MFA, student single session, Paymob sandbox if payments are enabled.
- Run backup/restore drill to a disposable database.

## Gate D — production before students
- Deploy production without announcing/opening enrollment.
- Run `deploy/production-acceptance.sh`.
- Perform one controlled admin login and one test student login.
- Verify Stream upload reaches `ready` before publish and raw video URL is not exposed.
- Verify protected file returns access for enrolled test student and denial for unauthorized account.
- If Paymob is enabled, verify HMAC and one controlled transaction before accepting live payments.
- Confirm backup timestamp and restore drill evidence.

## Gate E — cutover
Only after A–D pass:
- Attach/verify `api.ragab-seddik.com` and `student.ragab-seddik.com`.
- Keep `ragab-seddik.com` / `www` backend fallback during the current migration stage.
- Monitor 5xx, DB pool timeouts, Redis reconnects, login failures, upload failures, and payment webhook failures.
- Have rollback ready: previous Worker version + previous Pages deployment + database restore procedure.

A failed gate means **do not open the platform to students** until the failure is resolved.
