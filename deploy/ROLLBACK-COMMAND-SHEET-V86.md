# V86 Rollback Command Sheet

> **Operator-controlled only.** Do not automate destructive database restore or DNS mutation from this package.

## Immediate rollback triggers
Rollback immediately for sustained `/ready` failure, widespread 5xx, login/session failure, DB/Redis unavailability, protected media failure, or payment/webhook corruption.

## Sequence
1. Freeze new deployments and record UTC timestamp + incident owner.
2. Route traffic back to the **previous verified release** using your Cloudflare deployment/version rollback control.
3. Restore the previous Pages deployment if the student frontend caused the incident.
4. Re-run `/health`, `/ready`, anonymous session 401, login, protected video, and logout checks.
5. **Do not restore PostgreSQL by default.** Application rollback and database restore are separate decisions.
6. Restore the database only if data/schema corruption is proven, using the verified backup/restore drill and a specifically approved restore target.
7. Revert DNS only if the incident is caused by the custom-domain/routing cutover; use the exact pre-recorded DNS snapshot.
8. Keep payments disabled if webhook integrity or entitlement activation is uncertain.
9. Record recovery evidence before reopening traffic.

## Required evidence before a cutover window
- Previous backend release identifier/version.
- Previous Pages deployment identifier.
- Fresh PostgreSQL backup identifier and successful restore-drill evidence.
- DNS/custom-domain snapshot.
- Rollback owner and second approver.
- Monitoring owner for the observation window.

This file intentionally contains no account IDs, tokens, passwords, or destructive one-click commands.
