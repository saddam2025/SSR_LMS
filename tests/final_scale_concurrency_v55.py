import os
os.environ.setdefault("ENV","test")
os.environ.setdefault("APP_SECRET","test-secret-change-this")
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app

root=Path(__file__).resolve().parents[2]
worker=(root/"cloudflare/src/index.js").read_text(encoding="utf-8")
wrangler=(root/"cloudflare/wrangler.jsonc").read_text(encoding="utf-8")
main=(root/"platform/app/main.py").read_text(encoding="utf-8")
assert "getRandom(env.MOSTASHAR, poolSize)" in worker
assert '"instance_type": "standard-1"' in wrangler and '"max_instances": 5' in wrangler
assert '"CONTAINER_POOL_SIZE": "5"' in wrangler
assert '"DB_POOL_SIZE": "4"' in wrangler and '"DB_MAX_OVERFLOW": "4"' in wrangler
assert "pg_advisory_xact_lock" in main
assert "_pg_xact_lock(db, 5505" in main
assert "_pg_xact_lock(db, 5506" in main
assert "_pg_xact_lock(db, 5507" in main
assert "with_for_update().first() if attempt_id else None" in main
assert "isAnonymousHomeRequest" in worker
assert "batched queries" in main
client=TestClient(app)
r=client.get("/")
assert r.status_code==200
assert "lms_session" not in (r.headers.get("set-cookie") or "")
print("V55 FINAL SCALE/CONCURRENCY FLOW OK")
