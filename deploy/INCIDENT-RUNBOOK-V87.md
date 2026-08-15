# V87 Incident Runbook

## Severity
- **SEV-1:** platform unavailable, login broadly broken, protected content inaccessible, confirmed payment/entitlement corruption, or suspected secret compromise.
- **SEV-2:** major degraded feature with workaround, elevated 5xx, Stream/R2/Redis degradation.
- **SEV-3:** isolated user/lesson issue with no systemic impact.

## First 10 minutes
1. Record UTC start time, affected domains/features, release identifier, and incident owner.
2. Stop further deployments and configuration changes.
3. Check `/health`, `/ready`, frontend reachability, DB/Redis, Stream/R2 and webhook error signals.
4. For SEV-1 tied to the new release, use `ROLLBACK-COMMAND-SHEET-V86.md`.
5. Do **not** restore the database unless data/schema corruption is established separately.
6. If payment integrity is uncertain, disable new payment initiation while preserving evidence and webhook logs.
7. If a secret may be exposed, rotate it through the provider secret store; never paste it into incident notes.

## Evidence to preserve
Request IDs, UTC timestamps, HTTP status distribution, provider request/event IDs, deployment IDs, database error class, and anonymized affected-user counts. Do not store passwords, session cookies, access tokens, full card/payment data, or private student content.

## Recovery
Recovery requires stable readiness, successful login/logout, protected lesson playback, and—when relevant—verified payment/webhook entitlement behavior. Keep observation active after recovery.
