import os
os.environ.setdefault('ENV','test'); os.environ.setdefault('APP_SECRET','test-secret-change-this')
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
ROOT=Path(__file__).resolve().parents[1]
db=(ROOT/'app/db.py').read_text(); runtime=(ROOT/'app/routers/learning_runtime.py').read_text(); commerce=(ROOT/'app/routers/commerce.py').read_text(); start=(ROOT/'container-start.sh').read_text(); env=(ROOT/'.env.railway.example').read_text()
assert 'DB_POOL_SIZE' in db and 'DB_MAX_OVERFLOW' in db and 'pool_pre_ping=True' in db
assert 'pg_advisory_xact_lock' in runtime and 'with_for_update()' in runtime
assert 'pg_advisory_xact_lock' in commerce and 'with_for_update()' in commerce
assert 'WEB_CONCURRENCY' in start and 'UVICORN_BACKLOG' in start
assert 'DB_POOL_SIZE=5' in env and 'DB_MAX_OVERFLOW=5' in env
client=TestClient(app); r=client.get('/'); assert r.status_code==200; assert 'lms_session' not in (r.headers.get('set-cookie') or '')
print('RAILWAY SCALE/CONCURRENCY FLOW OK')
