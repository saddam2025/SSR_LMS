# V79 Production backup / restore

## PostgreSQL
Run `ops/backup-postgres.sh` from a trusted operations host with `DATABASE_URL` set. The script creates a PostgreSQL custom-format dump plus SHA-256 checksum. Copy backups to storage that is separate from the application database and retain multiple restore points.

Restore only during a maintenance window. Set `RESTORE_FILE`, `DATABASE_URL`, and the explicit guard `CONFIRM_RESTORE=YES_RESTORE_MOSTASHAR`, then run `ops/restore-postgres.sh`. Always restore into a staging database first and run `/ready` plus the release smoke tests before a production restore.

## Cloudflare R2
Enable bucket object versioning / retention in Cloudflare where available and keep database backups separate from the R2 bucket. The database stores media metadata; R2 stores the protected objects, so disaster recovery requires both.

## Minimum operating policy
- Automated PostgreSQL backup at least daily; more frequently if payments/enrollments are busy.
- Keep at least one off-provider copy.
- Test restore periodically; an untested backup is not a recovery plan.
- Rotate application, Cloudflare, Paymob and webhook secrets after any suspected exposure.
