# V88 Production Environment Requirements

This document lists variable **names and purpose only**. Do not place real values in Git, ZIP, chat, screenshots, or support tickets.

## Core
`ENV=production`, `APP_SECRET`, `PUBLIC_BASE_URL`, `ALLOWED_HOSTS`, `CORS_ORIGINS`, `DATABASE_URL`, `REDIS_URL`.

## Cloudflare media
`CF_ACCOUNT_ID`, `CF_STREAM_API_TOKEN`, `CF_STREAM_CUSTOMER_CODE`, `CF_EDGE_SIGNING_SECRET`.

## R2 / S3-compatible private storage
`S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`.

## Bootstrap administration
`ADMIN_EMAIL`, `ADMIN_PASSWORD`. Keep `RUN_SEED_ON_START=false` for normal production startup.

## Payments
Paymob variables required by the configured integration: secret/public key, HMAC secret and integration ID. Keep payment disabled until test-mode webhook + entitlement evidence is PASS.

## Optional providers
FCM/SMS/WhatsApp variables are required only when those providers are enabled.

Use provider/Cloudflare secret stores for real values. V81/V82 gates must validate readiness without printing them.
