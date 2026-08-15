import json
import os
from pathlib import Path

os.environ.setdefault("ENV", "test")
os.environ.setdefault("APP_SECRET", "test-secret-change-this")

from fastapi.testclient import TestClient
from app.main import app

ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
assert (ROOT/'VERSION').read_text().strip() in {'V80','V81'}
assert (REPO/'VERSION').read_text().strip() in {'V80','V81'}

prod=json.loads((REPO/'cloudflare/wrangler.jsonc').read_text())
stage=json.loads((REPO/'cloudflare/wrangler.staging.jsonc').read_text())
prod_domains={x['pattern'] for x in prod['routes']}
assert 'api.ragab-seddik.com' in prod_domains
assert 'ragab-seddik.com' in prod_domains
assert prod['vars']['FRONTEND_ORIGINS'] == 'https://student.ragab-seddik.com'
assert prod['vars']['FRONTEND_PRIMARY_ORIGIN'] == 'https://student.ragab-seddik.com'
assert stage['routes'] == [{'pattern':'staging-api.ragab-seddik.com','custom_domain':True}]
assert stage['vars']['FRONTEND_ORIGINS'] == 'https://staging-student.ragab-seddik.com'
assert stage['vars']['PUBLIC_BASE_URL'] == 'https://staging-api.ragab-seddik.com'

worker=(REPO/'cloudflare/src/index.js').read_text()
assert 'function allowedHost(hostname, env)' in worker
assert 'String(runtimeEnv.PUBLIC_BASE_URL' in worker
assert 'String(runtimeEnv.FRONTEND_ORIGINS' in worker

front=ROOT/'frontend'
assert 'https://api.ragab-seddik.com' in (front/'config.js').read_text()
assert 'Content-Security-Policy:' in (front/'_headers').read_text()
assert (ROOT/'deploy/staging-acceptance.sh').exists()
assert (ROOT/'deploy/backup-restore-drill.sh').exists()
assert (ROOT/'deploy/production-cutover-checklist.md').exists()

client=TestClient(app)
r=client.get('/health')
assert r.status_code == 200
assert r.json().get('version') in {'V80','V81'}

seen=set()
for route in app.routes:
    methods=getattr(route,'methods',None); path=getattr(route,'path',None)
    if not methods or not path: continue
    for method in methods:
        if method in {'HEAD','OPTIONS'}: continue
        key=(method,path)
        assert key not in seen, key
        seen.add(key)
print('V80 DEPLOYMENT FINALIZATION TEST OK', {'routes':len(seen)})
