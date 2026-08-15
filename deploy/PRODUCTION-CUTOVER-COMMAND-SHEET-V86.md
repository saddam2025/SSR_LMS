# V86 Controlled Production Cutover

## Hard gate
Do **not** enter the cutover window unless V85 returns `GO_TO_CUTOVER_WINDOW` from real V84 staging evidence and production readiness.

## Pre-cutover
1. Freeze changes.
2. Build and verify `RELEASE-MANIFEST-V86.json` / `SHA256SUMS-V86.txt`.
3. Run `npm ci && npm run check` in the Cloudflare project.
4. Take a fresh PostgreSQL backup and record its identifier.
5. Confirm the previous backend and Pages releases are still available.
6. Record current DNS/custom-domain routing.
7. Confirm monitoring and rollback owners.

## Controlled sequence
1. Deploy backend/API release.
2. Confirm `/health` and `/ready`.
3. Deploy student Pages artifact.
4. Run `deploy/production-acceptance.sh`.
5. Run `deploy/post-cutover-monitor.sh` for the observation window.
6. Perform one controlled student flow: login → entitled course → protected video → logout.
7. Perform a controlled payment only when payment monitoring and webhook verification are active.
8. Keep legacy public/admin fallback attached during the first student Pages release.

## Abort / rollback
Any sustained readiness failure, broad 5xx, auth/session breakage, protected media failure, or payment integrity issue means stop and follow `ROLLBACK-COMMAND-SHEET-V86.md`.

## Important
This package prepares commands and evidence. It does not mutate DNS or deploy resources automatically.
