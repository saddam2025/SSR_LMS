# V87 Launch Day Operations

## Before opening traffic
- V84 real Staging Operational Acceptance = GO.
- V85 = `GO_TO_CUTOVER_WINDOW`.
- V86 release manifest verifies.
- Fresh PostgreSQL backup recorded; restore drill already proven.
- Previous backend and Pages releases available.
- DNS/custom-domain snapshot recorded.
- Monitoring and rollback owners assigned.

## Observation windows
- **0–30 min:** health/readiness/frontend every minute; watch auth, DB/Redis, Stream and webhook errors.
- **30 min–2 h:** every 5 minutes plus controlled student flow.
- **2–6 h:** every 15 minutes; review 5xx, latency, login failures, video failures, payment/webhook outcomes.
- **6–24 h:** hourly operational review; keep rollback artifacts available.

## Launch checks
Student: login → course entitlement → protected lesson/video → progress → logout.
Admin: login/MFA → course/lesson visibility → reports.
Media: one controlled upload/playback check if operationally appropriate.
Payments: only after webhook verification and monitoring are active.

## Stop conditions
Sustained `/ready` failure, broad 5xx/auth breakage, protected-media outage, payment entitlement corruption, or evidence of security compromise. Follow Incident Runbook and V86 rollback sheet.
