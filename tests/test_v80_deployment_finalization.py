import json, os
from pathlib import Path
os.environ.setdefault('ENV','test'); os.environ.setdefault('APP_SECRET','test-secret-change-this')
from fastapi.testclient import TestClient
from app.main import app
ROOT=Path(__file__).resolve().parents[1]
EXPECTED=(ROOT/'VERSION').read_text().strip()
assert EXPECTED.startswith('V')
assert (ROOT/'Dockerfile').exists() and (ROOT/'railway.toml').exists() and (ROOT/'container-start.sh').exists()
assert 'healthcheckPath = "/ready"' in (ROOT/'railway.toml').read_text()
assert 'python -m app.deploy_prepare' in (ROOT/'railway.toml').read_text()
front=ROOT/'frontend'
assert 'window.location.origin' in (front/'config.js').read_text()
assert 'Content-Security-Policy:' in (front/'_headers').read_text()
assert (ROOT/'deploy/staging-acceptance.sh').exists()
assert (ROOT/'deploy/backup-restore-drill.sh').exists()
assert (ROOT/'deploy/production-cutover-checklist.md').exists()
client=TestClient(app); r=client.get('/health')
assert r.status_code==200 and r.json().get('version')==EXPECTED
seen=set()
for route in app.routes:
    methods=getattr(route,'methods',None); path=getattr(route,'path',None)
    if not methods or not path: continue
    for method in methods:
        if method in {'HEAD','OPTIONS'}: continue
        key=(method,path); assert key not in seen,key; seen.add(key)
print('DEPLOYMENT FINALIZATION TEST OK', {'release':EXPECTED,'routes':len(seen)})
