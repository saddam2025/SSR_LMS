# Mostashar V59 — Separated Architecture

## What changed
- Added an independent `frontend/` suitable for Cloudflare Pages.
- Added credentialed, allowlisted CORS support in FastAPI.
- Added `/api/v1/session` for the frontend bootstrap and CSRF acquisition.
- Added `/api/v1/logout` with CSRF validation.
- Student/parent post-login redirect can target the independent frontend through `FRONTEND_PRIMARY_ORIGIN`; staff/admin remain on the mature Jinja interface during migration.
- Existing server-rendered pages remain intact as a rollback/fallback path.

## Recommended production routing
- `www.ragab-seddik.com` -> Cloudflare Pages frontend
- `api.ragab-seddik.com` -> FastAPI backend
- Cloudflare Stream -> video
- Cloudflare R2/private object storage -> protected files
- PostgreSQL + Redis -> backend only

## Migration rule
Move one user surface at a time and keep authorization, payments, upload ownership, media signing, and business rules in the backend.
