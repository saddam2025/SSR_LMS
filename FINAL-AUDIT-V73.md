# Mostashar V73 — Admin Domains Extraction

V73 continues the modular backend migration from V72.

## Extracted domains
- `app/routers/communications.py`: admin communications campaign UI and send/quick-send HTTP routes.
- `app/services/communications.py`: audience resolution and hardened outbound webhook delivery.
- `app/routers/reports.py`: student performance report HTML, XLSX and PDF endpoints.
- `app/services/reports.py`: student performance aggregation, XLSX generation and Arabic PDF shaping helpers.

## Security / compatibility
- Existing public URLs and HTTP methods are unchanged.
- Role checks and CSRF enforcement remain server-side.
- Outbound message webhooks require HTTPS and reject local/private/reserved destinations to reduce SSRF exposure.
- Student performance logic remains available to legacy admin pages through a thin compatibility wrapper.
- Route duplication is explicitly tested.

## Size
`app/main.py` reduced from 2823 lines in V72 to 2614 lines in V73.

## Regression gate
Passed locally:
- Student Reports V13
- Communication Center V15
- Auth HTTP Contract V53
- Media Integrity V56
- Resumable Lecture Upload V57
- Navigation Contract
- Learning Runtime Full Decoupling V72
- V73 Admin Domains Extraction
- Python compileall

External production integrations still require live acceptance testing with production credentials and domains.
