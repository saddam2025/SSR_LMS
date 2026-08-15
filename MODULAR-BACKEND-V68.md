# Mostashar V68 — Auth Router & Service Extraction

V68 extracts authentication/account HTTP endpoints from `app/main.py` into `app/routers/auth.py` and extracts reusable authentication domain services into `app/services/auth.py`.

## Extracted HTTP routes
- Registration
- Login / logout
- Password reset flow
- TOTP MFA challenge and enrollment
- Account password change
- OTP phone login

## Extracted services
- Phone normalization
- OTP creation and provider-neutral SMS delivery
- Device/session establishment
- Student single-session enforcement
- Device-limit enforcement
- Production-safe frontend landing redirects
- PostgreSQL advisory lock used during session creation

## Security properties preserved
- HttpOnly session cookie
- CSRF validation on state-changing browser requests
- Device fingerprint validation
- Account lockout/rate limiting
- MFA enforcement
- Session revocation on password reset/change
- OTP expiration/attempt limits
- No secrets exposed to frontend

`app/main.py` reduced from 4043 lines in V67 to 3672 lines in V68.
