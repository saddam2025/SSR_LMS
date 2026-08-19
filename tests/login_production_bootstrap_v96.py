import os, subprocess, sys, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def run(cmd, env):
    p=subprocess.run(cmd,cwd=ROOT,env=env,text=True,capture_output=True)
    if p.returncode:
        print(p.stdout); print(p.stderr,file=sys.stderr); raise SystemExit(p.returncode)
    return p.stdout

with tempfile.TemporaryDirectory() as td:
    db=Path(td)/'prod.db'
    env=os.environ.copy()
    env.update({
        'ENV':'production','DATABASE_URL':f'sqlite:///{db}',
        'ADMIN_EMAIL':'owner@example.test','ADMIN_PASSWORD':'StrongInitial123!45',
        'ADMIN_NAME':'Owner','APP_SECRET':'x'*80,'PUBLIC_BASE_URL':'https://ragab-seddik.com',
        'ALLOWED_HOSTS':'ragab-seddik.com','REDIS_URL':'redis://example.invalid:6379',
        'REQUIRE_STAFF_MFA':'true','SEPARATED_FRONTEND_ENABLED':'false',
    })
    # Importing normal production preflight would require real Redis; bootstrap itself must be DB-only/idempotent.
    run([sys.executable,'-m','app.bootstrap_admin'],env)
    run([sys.executable,'-m','app.bootstrap_admin'],env)
    code='''from app.db import SessionLocal\nfrom app.models import User\ndb=SessionLocal(); rows=db.query(User).all(); assert len(rows)==1; u=rows[0]; assert u.email=="owner@example.test" and u.role=="admin" and u.is_active; print("ok")'''
    assert 'ok' in run([sys.executable,'-c',code],env)
print('V96 PRODUCTION LOGIN BOOTSTRAP: PASS')
