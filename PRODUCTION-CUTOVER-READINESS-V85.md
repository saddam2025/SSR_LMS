# V85 Production Cutover Readiness

V85 is a fail-closed decision gate. It does **not** deploy, mutate DNS, or expose secrets.

## Mandatory pre-cutover GO inputs
1. A real V84 staging operational acceptance report with `go: true`.
2. Production secret readiness passes with production-only values.
3. Rollback evidence passes: owner assigned, previous release available, database restore path verified, DNS rollback steps verified.
4. Monitoring evidence passes: health/error/DB+Redis/Stream+webhook monitoring ready.
5. A controlled first-user acceptance plan/evidence is prepared; after cutover it must be executed immediately.

Run:

```bash
cd platform
sh deploy/v85-go-no-go.sh \
  artifacts/v84-operational-acceptance.json \
  /secure/production.env \
  artifacts/production-evidence
```

Only `GO_TO_CUTOVER_WINDOW` permits entering the controlled cutover window. It is not itself proof that production is healthy after DNS changes.

## Cutover window sequence
1. Freeze content/admin changes for the short cutover window.
2. Take a fresh production backup and verify the artifact exists.
3. Confirm V84 staging evidence is unchanged and valid.
4. Deploy the exact approved V85 artifact/commit; do not rebuild from a different source tree.
5. Attach/verify production API and Pages custom domains.
6. Run `deploy/production-acceptance.sh` immediately.
7. Run `deploy/post-cutover-monitor.sh` during the observation window.
8. Execute the controlled production test student flow: login → course → protected video → logout.
9. Verify payment/webhook only with a controlled transaction before announcing launch.
10. Open access progressively; do not remove the legacy fallback in the same cutover.

## Immediate rollback triggers
Rollback instead of debugging live if any of the following persists beyond a short confirmation retry:
- `/ready` is not 200 or repeated 5xx appears.
- Student login/session/CORS is broken.
- PostgreSQL or Redis is unavailable or pool errors are sustained.
- Protected media grants/playback fail for enrolled users or become accessible to unauthorized users.
- Payment webhook validation/entitlement activation fails.
- A deployment points at the wrong environment/database/bucket.

Rollback order: stop traffic expansion → restore prior app release/routes → restore DNS/custom-domain target if changed → restore database only when the incident actually requires data rollback and after preserving incident evidence.
