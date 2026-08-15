# V88 Final Release Candidate — Deployment Handoff

## Artifact identity
1. Verify the ZIP SHA-256 supplied with the release.
2. Extract once into a clean directory.
3. Run `python deploy/verify-release-manifest.py --manifest RELEASE-MANIFEST-V88.json`.
4. Do not edit source after verification. Any edit creates a new release candidate.

## Required gates
1. Static/contract tests and Production Release Gate.
2. `npm ci && npm run check` for the Cloudflare project in the deployment environment.
3. V81 secrets readiness.
4. V82 real infrastructure validation.
5. V83 staging bring-up.
6. V84 real Staging Operational Acceptance = GO.
7. V85 Production Cutover Readiness = `GO_TO_CUTOVER_WINDOW`.
8. V86 controlled cutover/rollback sheets.
9. V87 launch monitoring and incident ownership.

## Deployment order
- PostgreSQL/Redis and provider resources already provisioned and validated.
- Backend/API production deployment.
- `/health` + `/ready`.
- Student Pages production artifact.
- Production acceptance.
- Controlled first student flow.
- Payment only after webhook monitoring is confirmed.
- 24-hour launch observation.

## Non-negotiable
V88 is a release candidate package, not proof that real infrastructure passed. Do not open production traffic while V84/V85 remain NO-GO.
