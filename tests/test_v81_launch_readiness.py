import json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault('ENV','test')
os.environ.setdefault('APP_SECRET','test-secret-change-this')
from fastapi.testclient import TestClient
from app.main import app

assert (ROOT/'VERSION').read_text().strip()=='V81'
assert (REPO/'VERSION').read_text().strip()=='V81'
assert (ROOT/'deploy/secret-readiness.py').exists()
assert (ROOT/'deploy/production-acceptance.sh').exists()
assert (ROOT/'deploy/LAUNCH-READINESS-V81.md').exists()

prod=json.loads((REPO/'cloudflare/wrangler.jsonc').read_text())
stage=json.loads((REPO/'cloudflare/wrangler.staging.jsonc').read_text())
assert prod['vars']['STATIC_CACHE_VERSION'].startswith('v81-')
assert stage['vars']['STATIC_CACHE_VERSION'].startswith('v81-staging-')
assert prod['vars']['RUN_SEED_ON_START']=='false'
assert stage['vars']['RUN_SEED_ON_START']=='false'
assert prod['vars']['FRONTEND_PRIMARY_ORIGIN'] != stage['vars']['FRONTEND_PRIMARY_ORIGIN']

# Secret readiness: complete, isolated dummy files pass; same DB must fail.
def env_text(stage=False, same_db=False):
    host='staging-api.ragab-seddik.com' if stage else 'api.ragab-seddik.com'
    front='staging-student.ragab-seddik.com' if stage else 'student.ragab-seddik.com'
    suffix='stage' if stage else 'prod'
    db_suffix='prod' if same_db else suffix
    vals={
        'ENV':'production','APP_SECRET':('S' if stage else 'P')*70,
        'CF_EDGE_SIGNING_SECRET':('E' if stage else 'F')*40,
        'CF_STREAM_CUSTOMER_CODE':'customer-'+suffix,'CF_ACCOUNT_ID':'account-'+suffix,
        'CF_STREAM_API_TOKEN':'token-'+suffix,'DATABASE_URL':f'postgresql://u:p@db/{db_suffix}',
        'REDIS_URL':f'rediss://redis/{suffix}','ADMIN_EMAIL':f'admin-{suffix}@example.com',
        'ADMIN_PASSWORD':'password-'+suffix+'-long-enough','S3_ENDPOINT_URL':'https://acct.r2.cloudflarestorage.com',
        'S3_BUCKET':'bucket-'+suffix,'S3_ACCESS_KEY_ID':'access-'+suffix,'S3_SECRET_ACCESS_KEY':'secret-'+suffix,
        'PUBLIC_BASE_URL':'https://'+host,'FRONTEND_PRIMARY_ORIGIN':'https://'+front,
        'RUN_SEED_ON_START':'false','REQUIRE_STAFF_MFA':'true','ALLOW_DIRECT_VIDEO_PROXY':'false',
    }
    return ''.join(f'{k}={v}\n' for k,v in vals.items())

with tempfile.TemporaryDirectory() as td:
    prodp=Path(td)/'prod.env'; stagep=Path(td)/'stage.env'
    prodp.write_text(env_text(False)); stagep.write_text(env_text(True))
    cmd=[sys.executable,str(ROOT/'deploy/secret-readiness.py'),'--production',str(prodp),'--staging',str(stagep)]
    r=subprocess.run(cmd,capture_output=True,text=True)
    assert r.returncode==0, r.stdout+r.stderr
    stagep.write_text(env_text(True,same_db=True))
    r=subprocess.run(cmd,capture_output=True,text=True)
    assert r.returncode!=0
    assert 'DATABASE_URL must differ' in r.stdout
    assert 'postgresql://u:p@db/prod' not in r.stdout

client=TestClient(app)
r=client.get('/health')
assert r.status_code==200 and r.json().get('version')=='V81'
assert r.headers.get('x-request-id')

seen=set()
for route in app.routes:
    methods=getattr(route,'methods',None); path=getattr(route,'path',None)
    if not methods or not path: continue
    for method in methods:
        if method in {'HEAD','OPTIONS'}: continue
        key=(method,path); assert key not in seen,key; seen.add(key)
print('V81 LAUNCH READINESS TEST OK', {'routes':len(seen)})
