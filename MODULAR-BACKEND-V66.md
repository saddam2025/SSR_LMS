# V66 — Shared Request Context Extraction

V66 removes cross-cutting authentication/request logic from `app/main.py` and places it in `app/request_context.py`.

Extracted responsibilities:
- trusted client IP resolution
- active-session validation and bounded last-seen touch
- device fingerprint enforcement
- current-user resolution
- `require_user` / `require_role`
- shared template context
- audit-log writes

Compatibility:
- `app.main` re-exports the same callable names so existing routes/tests stay compatible.
- `app.state` compatibility bindings are retained for older modules during gradual migration.
- New modular routers (`system`, `support`) import request-context functions directly, reducing coupling to the application object.
