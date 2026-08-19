import os, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT)); os.environ.setdefault('ENV','test'); os.environ.setdefault('APP_SECRET','test-secret-change-this')
from fastapi.testclient import TestClient
from app.main import app
EXPECTED=(ROOT/'VERSION').read_text().strip()
assert (ROOT/'deploy/secret-readiness.py').exists(); assert (ROOT/'deploy/production-acceptance.sh').exists()
env=(ROOT/'.env.railway.example').read_text()
for x in ('ENV=production','RUN_SEED_ON_START=false','REQUIRE_STAFF_MFA=true','DATABASE_URL=${{Postgres.DATABASE_URL}}','REDIS_URL=${{Redis.REDIS_URL}}'):
    assert x in env

def env_text(stage=False,same_db=False):
    host='staging-api.ragab-seddik.com' if stage else 'api.ragab-seddik.com'; front='staging-student.ragab-seddik.com' if stage else 'student.ragab-seddik.com'; suffix='stage' if stage else 'prod'; db_suffix='prod' if same_db else suffix
    vals={'ENV':'production','APP_SECRET':('S' if stage else 'P')*70,'CF_EDGE_SIGNING_SECRET':('E' if stage else 'F')*40,'CF_STREAM_CUSTOMER_CODE':'customer-'+suffix,'CF_ACCOUNT_ID':('a' if stage else 'b')*32,'CF_STREAM_API_TOKEN':'token-'+suffix+'-'+'x'*24,'DATABASE_URL':f'postgresql://u:p@db/{db_suffix}','REDIS_URL':f'rediss://redis/{suffix}','ADMIN_EMAIL':f'admin-{suffix}@example.com','ADMIN_PASSWORD':'password-'+suffix+'-long-enough','S3_ENDPOINT_URL':'https://acct.r2.cloudflarestorage.com','S3_BUCKET':'bucket-'+suffix,'S3_ACCESS_KEY_ID':'access-'+suffix,'S3_SECRET_ACCESS_KEY':'secret-'+suffix,'PUBLIC_BASE_URL':'https://'+host,'FRONTEND_PRIMARY_ORIGIN':'https://'+front,'RUN_SEED_ON_START':'false','REQUIRE_STAFF_MFA':'true','ALLOW_DIRECT_VIDEO_PROXY':'false'}
    return ''.join(f'{k}={v}\n' for k,v in vals.items())
with tempfile.TemporaryDirectory() as td:
    prodp=Path(td)/'prod.env'; stagep=Path(td)/'stage.env'; prodp.write_text(env_text(False)); stagep.write_text(env_text(True))
    cmd=[sys.executable,str(ROOT/'deploy/secret-readiness.py'),'--production',str(prodp),'--staging',str(stagep)]
    r=subprocess.run(cmd,capture_output=True,text=True); assert r.returncode==0,r.stdout+r.stderr
    stagep.write_text(env_text(True,same_db=True)); r=subprocess.run(cmd,capture_output=True,text=True); assert r.returncode!=0; assert 'DATABASE_URL must differ' in r.stdout; assert 'postgresql://u:p@db/prod' not in r.stdout
client=TestClient(app); r=client.get('/health'); assert r.status_code==200 and r.json().get('version')==EXPECTED and r.headers.get('x-request-id')
print('LAUNCH READINESS TEST OK', {'release':EXPECTED})
