# Mostashar V67 — Media & Commerce Router Extraction

V67 continues the modular backend migration without changing public URLs.

## Extracted routers
- `app/routers/media.py`: resumable Cloudflare Stream, protected attachment upload/delete, protected media delivery.
- `app/routers/commerce.py`: checkout, Paymob webhook, payment completion, commerce dashboard, coupons and subscriptions.

## Compatibility and security
Existing endpoint paths and methods are preserved. Authorization, CSRF, course ownership, entitlement checks, media signatures and watermark controls remain server-side. V57 Stream test seams remain temporarily compatible during migration.

## Result
`app/main.py` reduced from 4477 lines in V66 to 4043 lines in V67.
