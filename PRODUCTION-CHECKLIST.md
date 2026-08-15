# Production launch gate — Ragab Seddik LMS

The application now refuses unsafe `ENV=production` startup unless the core baseline is valid: HTTPS public URL, >=64-character app secret, PostgreSQL, Redis, non-placeholder administrator credentials, and host allow-list derivation.

Before commercial launch, configure real provider credentials for any feature you enable:
- Paymob keys/HMAC/integration id for paid checkout.
- SMS webhook/provider credentials for OTP by phone.
- S3-compatible private storage if local media is not appropriate for the deployment.
- DRM vendor/license server if studio-grade DRM is required.
- VIDEO_ALLOWED_HOSTS for external video providers.

Admin can verify runtime status at `/admin/system-status`.

No software can be guaranteed to contain zero vulnerabilities. Run dependency scanning, SAST/DAST and an independent penetration test against the deployed production environment before launch, and repeat after material changes.
