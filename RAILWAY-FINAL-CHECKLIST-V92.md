# V92 Railway Final Checklist

1. Create Railway project.
2. Add PostgreSQL and Redis services.
3. Deploy this source using the root Dockerfile.
4. Set `DATABASE_URL` and `REDIS_URL` as Railway reference variables.
5. Set `ENV=production` on both staging and production so production safety gates run.
6. Add `healthcheck.railway.app` to `ALLOWED_HOSTS`; add the temporary Railway domain while it is in use.
7. Configure Cloudflare Stream and R2 variables before first real upload.
8. Use `/ready` as Railway healthcheck.
9. Verify `/health`=200, `/ready`=200, anonymous session=401, login, course access, protected lesson, upload, and logout.
10. Run R2 canary, TUS resume test, PostgreSQL backup/restore drill, and Paymob test-mode transaction on Staging.
11. Do not open production until Staging operational acceptance is GO.
