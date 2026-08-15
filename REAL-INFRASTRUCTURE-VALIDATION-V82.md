# V82 — Real Infrastructure Validation

V82 does not mark the platform production-ready merely because local tests pass. The launch decision is based on the deployed resources.

## Required sequence

1. Run `deploy/secret-readiness.py` against Production and Staging env files. Secret values are never printed.
2. Run `deploy/infrastructure-validation.py` against **Staging**. It performs PostgreSQL `SELECT 1` + schema presence, Redis `PING`, R2 bucket access, Cloudflare Stream API authentication, and structural Paymob configuration validation.
3. Re-run with `--write-canary` to verify R2 put/get/delete using a temporary `_v82_canary/` object.
4. Run `deploy/staging-acceptance.sh` against the deployed Staging domains.
5. Run `deploy/backup-restore-drill.sh` using a disposable restore database. Never point the restore URL at Production.
6. Perform one synthetic **Paymob test-mode** payment and verify webhook/HMAC + subscription activation. The generic infrastructure validator deliberately does not create a payment.
7. Upload one real test lecture through the resumable Stream/TUS flow, wait for `ready`, publish it, and play it as a subscribed student.
8. Only after all Staging checks pass, repeat the non-destructive infrastructure validator and `production-acceptance.sh` on Production.

## GO / NO-GO

**GO** requires: PostgreSQL, Redis, R2, Stream, domain/CORS/HTTPS acceptance, backup/restore drill, a real resumable upload, and a Paymob synthetic test to pass. Optional providers (for example FCM when disabled) may remain WARN only.

Any failed required check is **NO-GO**. Do not bypass the gate by disabling the check.

## Cloudflare notes

The platform's Stream upload flow intentionally uses Direct Creator Uploads/TUS so the browser does not receive the Cloudflare API token. R2 uses the S3-compatible endpoint and scoped R2 credentials. Use separate credentials/buckets or strict prefixes for Staging and Production.
