# Mostashar V64 — Modular Backend Foundation

V64 begins the backend decomposition without rewriting the stable platform.

## New structure

```text
app/
  routers/
    pwa.py
    system.py
    support.py
  services/
    support.py
  api_v1_*.py
  main.py
```

The migration is deliberately incremental. `main.py` remains the compatibility composition root while lower-risk route families are moved into APIRouters. Shared authentication, role, CSRF, template-context and audit helpers remain centralized for now and are exposed to migrated routers through explicit `app.state` callbacks.

## Why this approach

- avoids a high-risk all-at-once rewrite;
- preserves every existing URL during migration;
- lets legacy Jinja screens and separated frontend/API coexist;
- creates a repeatable pattern for later `media`, `payments`, `courses`, `quizzes`, `reports` and admin modules;
- keeps authorization decisions server-side.

## Next extraction candidates

1. Media/Cloudflare upload administration.
2. Commerce/payments/coupons/subscriptions.
3. Quiz authoring and question bank.
4. Course/lesson administration.
5. Reports and communications.
6. Move shared web authentication/context helpers out of `main.py` once route migration is sufficiently advanced.
