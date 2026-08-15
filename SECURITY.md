# Security Notes

## Threat model priorities
1. Account takeover
2. Credential stuffing / brute force
3. Shared student accounts
4. Unauthorized course/media access
5. Session theft and replay
6. Admin privilege abuse
7. Content leakage

## Implemented controls
- Argon2 password hashing
- CSRF tokens
- Signed secure session cookie settings
- Server-side session registry and revocation
- Session idle and absolute expiry
- Device registration and blocking
- Student device limit
- Redis-capable distributed login rate limiting
- Temporary account lockout
- Role-based authorization on protected routes
- Signed media authorization token bound to the active session
- Audit logging
- CSP, anti-framing, nosniff, referrer restriction, Permissions Policy
- HSTS in production
- Dynamic visible watermark and tiled watermark

## Important limitation
Browser JavaScript cannot reliably stop OS-level screenshots, external cameras, modified clients, or all screen recorders. Use DRM/secure video delivery for supported environments and retain per-user watermarking for leak attribution.
