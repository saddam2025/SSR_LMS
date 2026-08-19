# Deployment — V96 Critical Hardened Railway Handoff

## Supported production topology
- **One public web domain by default:** `https://ragab-seddik.com` (optionally `www` redirects to it).
- Railway Web Service runs this FastAPI source via the root `Dockerfile`.
- Railway PostgreSQL is the production database.
- Railway Redis is required for shared rate limits/cache/background-task coordination.
- Cloudflare R2 stores private PDFs/images/files.
- Cloudflare Stream handles resumable protected video upload/playback.
- A separate Pages frontend (`api.` / `student.`) is **optional legacy/advanced mode only** and must remain disabled unless explicitly deployed and accepted with `SEPARATED_FRONTEND_ENABLED=true`.

## Railway deployment order
1. Create one Railway project with Web, PostgreSQL and Redis services.
2. Connect the GitHub repository containing **this exact release** to the Web service.
3. Railway uses `railway.toml` from source:
   - Dockerfile build.
   - `python -m app.deploy_prepare` as the Pre-Deploy command.
   - `/ready` as the deployment healthcheck.
   - 300 second healthcheck timeout.
4. Copy variable names from `.env.railway.example` into Railway Variables and replace every placeholder with a real secret/value. Never commit real secrets.
5. Bind `DATABASE_URL=${{Postgres.DATABASE_URL}}` and `REDIS_URL=${{Redis.REDIS_URL}}` when that is the reference Railway exposes in your project; otherwise use Railway's Variables UI autocomplete and select the Redis connection URL it provides. Do not type a guessed variable name.
6. Keep `RUN_STARTUP_PREFLIGHT=false` on Railway: preparation already happens in Pre-Deploy.
7. Keep `RUN_SEED_ON_START=false` in production.
8. Do not define a fixed `PORT`; Railway injects it and `container-start.sh` binds Uvicorn to `0.0.0.0:$PORT`.
9. The temporary Railway hostname can be added to `ALLOWED_HOSTS` only while directly testing that hostname. `healthcheck.railway.app` is allowed automatically by the app and is also present in the example.

## Readiness model
- `/health`: lightweight process liveness/diagnostics.
- `/ready`: PostgreSQL + Redis readiness and is the Railway deployment healthcheck.
- Database schema/index bootstrap and initial production Admin bootstrap run in **Pre-Deploy**, so DB/config failures appear before the Network healthcheck stage instead of being hidden as a healthcheck timeout.

## R2 / uploads
- Keep `STORAGE_BACKEND=s3` and configure the real R2 endpoint/bucket/key/secret.
- Apply `R2-CORS-POLICY-V96.json` to the private bucket so PDF/image Direct-to-R2 uploads can run from the browser.
- Recommended Railway deploy setting: `STORAGE_PREFLIGHT_ROUNDTRIP=false`. R2 credentials/config are still validated by the production baseline, but a temporary R2 outage should not block the whole web deployment.
- Perform a real PDF/image upload during post-deploy acceptance. Set the roundtrip to `true` only if you intentionally want any transient R2 outage to block Pre-Deploy.

## Stream / protected video
- Configure `CF_ACCOUNT_ID`, `CF_STREAM_API_TOKEN`, `CF_STREAM_CUSTOMER_CODE`, `CF_EDGE_SIGNING_SECRET` and allowed origins/hosts.
- Keep `ALLOW_DIRECT_VIDEO_PROXY=false` in production.
- Deploy the included `cloudflare/stream-edge/` Worker for signed Stream playback.

## Mandatory acceptance before students
After the deployment is Active, verify `/health` and `/ready`, Admin MFA, Admin/Student/Parent login, PDF/image Direct-to-R2 upload, protected document access, resumable Stream video upload/playback, quiz auto-grading, logout/session revocation, and Railway CPU/RAM/DB connection behavior under a controlled concurrent test.

Local tests do not replace provider-side PostgreSQL/Redis/R2/Stream/DNS/TLS acceptance.

## Source integrity commands
```bash
python release_check.py
python deploy/verify-release-manifest.py --manifest RELEASE-MANIFEST-V96.json
python deploy/release-candidate-check.py
PYTHONPATH=. python -m pytest -q
```
