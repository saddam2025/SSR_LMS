# API v1

Stable application API prefix: `/api/v1`.

Current authenticated endpoints:
- `GET /api/v1/courses`
- `GET /api/v1/courses/{course_id}/lessons`
- `GET /api/v1/me/summary`

The browser session remains the authentication source for this release. A future mobile client should use a dedicated token/OAuth flow rather than copying browser cookies.

Operational endpoints:
- `GET /health` — liveness only, no database dependency.
- `GET /ready` — database and Redis readiness.
- `GET /internal/metrics` — admin-only application route counters/average latency.

Breaking API changes must use a new prefix (`/api/v2`) instead of changing v1 contracts in place.
