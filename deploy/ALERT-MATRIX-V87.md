# V87 Alert Matrix

| Signal | Warning | Critical | Operator action |
|---|---|---|---|
| `/ready` | 1 failed probe | 2 consecutive failures | investigate dependencies; rollback if release-related |
| HTTP 5xx | clear rise over baseline | sustained broad failure | freeze changes; inspect request IDs; rollback if needed |
| DB/Redis | intermittent errors | unavailable / pool exhaustion | protect writes; investigate provider/connectivity |
| Stream/R2 | upload/playback errors rising | protected media broadly unavailable | pause affected uploads; preserve provider IDs |
| Paymob webhook | delayed/retry increase | signature/entitlement mismatch | stop new payment initiation; reconcile safely |
| Auth | login failures rising | widespread login/session failure | inspect auth/Redis/DB; rollback if release-related |

Thresholds must be calibrated from real production baseline. V87 intentionally does not invent fixed traffic percentages before launch data exists.
