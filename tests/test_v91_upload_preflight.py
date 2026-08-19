import os, subprocess, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def base_env():
    env=os.environ.copy()
    env.update({
        "ENV":"production",
        "APP_SECRET":"a"*64,
        "PUBLIC_BASE_URL":"https://staging-api.ragab-seddik.com",
        "ALLOWED_HOSTS":"staging-api.ragab-seddik.com,healthcheck.railway.app",
        "DATABASE_URL":"postgresql://user:pass@db:5432/app",
        "REDIS_URL":"redis://redis:6379/0",
        "ADMIN_EMAIL":"admin@example.test",
        "ADMIN_PASSWORD":"VeryStrongPassword123!",
        "REQUIRE_STAFF_MFA":"true",
        "CLOUDFLARE_DEPLOYMENT":"true",
        "CF_EDGE_SIGNING_SECRET":"b"*40,
        "CF_ACCOUNT_ID":"c"*32,
        "CF_STREAM_API_TOKEN":"d"*40,
        "CF_STREAM_CUSTOMER_CODE":"customer-code-test",
        "VIDEO_ALLOWED_HOSTS":"cloudflarestream.com,videodelivery.net",
        "ALLOW_DIRECT_VIDEO_PROXY":"false",
        "FRONTEND_PRIMARY_ORIGIN":"https://staging-student.ragab-seddik.com",
        "FRONTEND_ORIGINS":"https://staging-student.ragab-seddik.com",
        "STORAGE_BACKEND":"s3",
        "S3_ENDPOINT_URL":"https://abcd.r2.cloudflarestorage.com",
    })
    for k in ("S3_BUCKET","S3_ACCESS_KEY_ID","S3_SECRET_ACCESS_KEY"):
        env.pop(k,None)
    return env

def test_r2_credentials_are_required_for_cloudflare_production():
    env=base_env()
    code="from app.production import production_status; import json; s=production_status(); print(json.dumps(s)); raise SystemExit(0 if not s['required']['cloudflare_r2_storage'] else 1)"
    p=subprocess.run([sys.executable,"-c",code],cwd=ROOT,env=env,capture_output=True,text=True)
    assert p.returncode == 0, p.stdout+p.stderr

def test_r2_credentials_make_required_check_pass():
    env=base_env()
    env.update({
        "S3_BUCKET":"mostashar-staging",
        "S3_ACCESS_KEY_ID":"key1234567890",
        "S3_SECRET_ACCESS_KEY":"secret12345678901234567890",
    })
    code="from app.production import production_status; s=production_status(); raise SystemExit(0 if s['required']['cloudflare_r2_storage'] else 1)"
    p=subprocess.run([sys.executable,"-c",code],cwd=ROOT,env=env,capture_output=True,text=True)
    assert p.returncode == 0, p.stdout+p.stderr
