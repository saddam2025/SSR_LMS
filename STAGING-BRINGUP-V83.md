# V83 — Staging Infrastructure Bring-Up

V83 turns the V82 infrastructure checks into a repeatable Staging bring-up process. It does **not** claim that Staging is live until the real resources and domains pass the gate.

## 1. Create isolated Staging resources

Use separate Staging PostgreSQL and Redis resources. Use a separate R2 bucket or a deliberately isolated Staging bucket/prefix and scoped credentials. Use a separate `APP_SECRET`, `CF_EDGE_SIGNING_SECRET`, admin password, and preferably scoped Cloudflare Stream/R2 credentials. Never copy Production secrets into Staging.

Copy `deploy/STAGING-ENV-TEMPLATE.env` to a private location outside source control and replace every `REPLACE_*` value.

## 2. Pre-deploy gate

```bash
cd platform
python deploy/staging-bringup.py --env-file /secure/staging.env --phase predeploy
```

For the explicit R2 put/get/delete canary:

```bash
python deploy/staging-bringup.py --env-file /secure/staging.env --phase predeploy --write-canary
```

The R2 write canary is opt-in. It writes a temporary canary object, reads it back, then deletes it.

## 3. Deploy Staging

Before deploying the Cloudflare Worker, run inside `cloudflare/`:

```bash
npm ci
npm run check
npx wrangler deploy --config wrangler.staging.jsonc
```

Build the Staging Pages output with the existing Pages builder, then deploy it to the project/domain intended for `staging-student.ragab-seddik.com`.

## 4. Post-deploy gate

After DNS and TLS are active:

```bash
cd platform
python deploy/staging-bringup.py --env-file /secure/staging.env --phase postdeploy
```

This adds DNS/TLS validation and the HTTP Staging acceptance contract on top of the infrastructure checks.

## 5. Manual gates that still block GO

Even when the automated V83 report says GO, launch remains blocked until all of these are completed and recorded:

- Backup → restore drill into a disposable Staging restore database.
- A real browser resumable/TUS upload to Cloudflare Stream, wait for `ready`, publish, and play it from a subscribed Staging student.
- A Paymob **test-mode** payment with correct webhook/HMAC verification and subscription activation.
- A final review that Staging uses different database, Redis, app/signing secrets, admin password, and public origins from Production.

Only after these gates pass should Production cutover be attempted.
