# Mostashar V84 — Staging Operational Acceptance

V84 is the final staging operations gate before any production cutover review.

## Required sequence

1. Provision isolated staging PostgreSQL, Redis, R2 and Stream credentials.
2. Deploy staging API and student frontend.
3. Run the V83 full automated gate.
4. Perform a real resumable Stream/TUS upload and playback test.
5. Perform backup → restore into a disposable database → integrity verification.
6. Perform one Paymob **Test Mode** payment and confirm the webhook activates the expected subscription exactly once.
7. Save only sanitized evidence JSON; never store credentials, card data, signed URLs, or full webhook payloads.
8. Run V84 operational acceptance.

## Evidence files

Use the schemas under `deploy/evidence-templates/`:

- `stream-tus.json`
- `backup-restore.json`
- `paymob-test.json`

Each file must explicitly report `go: true` and all required assertions as true. Missing evidence is a hard NO-GO.

## Command

```bash
cd platform
mkdir -p artifacts/evidence
# Copy the evidence templates and replace only the pass/fail fields after real tests.
V84_R2_WRITE_CANARY=true sh deploy/v84-staging-acceptance.sh /secure/staging.env artifacts/evidence
```

## GO rule

GO requires all of the following:

- V83 full automated bring-up = PASS
- real Stream/TUS resumable upload/playback/authorization = PASS
- backup/restore/integrity drill = PASS
- Paymob test payment/webhook/subscription activation = PASS

Any missing or failed gate means **NO-GO and remain on staging**.
