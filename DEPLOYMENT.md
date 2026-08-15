# Deployment — V80 Cloudflare Production Finalization

## Topology
- Public/legacy fallback: `ragab-seddik.com`, `www.ragab-seddik.com`
- Backend/API: `api.ragab-seddik.com` (Cloudflare Worker + Containers)
- Student frontend: `student.ragab-seddik.com` (Cloudflare Pages)
- Staging API: `staging-api.ragab-seddik.com`
- Staging student frontend: `staging-student.ragab-seddik.com`

The public fallback remains attached to the backend during the staged migration because the independent static frontend currently covers the student experience, not every public/admin page.

## Required gates
1. `python release_check.py`
2. `python deploy/validate-frontend-pages.py`
3. `python -m compileall -q app`
4. `cd ../cloudflare && npm ci && npm run check` on a Node 22+ / Docker deployment machine.
5. Deploy staging backend with `wrangler.staging.jsonc` and a staging Pages build.
6. Run `deploy/staging-acceptance.sh` against deployed staging.
7. Perform real Stream resumable upload, protected-file authorization, Paymob sandbox webhook, MFA/session tests.
8. Take a PostgreSQL backup and run `deploy/backup-restore-drill.sh` against a disposable restore database.
9. Only then deploy production and attach `student.ragab-seddik.com` to Pages.

Never commit real secrets. `RUN_SEED_ON_START` is intentionally false in V80 production/staging.
