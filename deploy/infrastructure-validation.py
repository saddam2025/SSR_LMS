#!/usr/bin/env python3
"""V82 real infrastructure validation.

Checks configured production/staging resources without printing credentials.
Default mode is non-destructive. Pass --write-canary to verify R2 write/read/delete.
"""
from __future__ import annotations
import argparse, json, os, re, sys, time, uuid
from pathlib import Path
from urllib.parse import urlparse


def parse_env(path: Path | None) -> dict[str, str]:
    env = dict(os.environ)
    if path:
        for raw in path.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def result(name: str, ok: bool, detail: str, *, required: bool = True) -> dict:
    return {'check': name, 'status': 'PASS' if ok else ('FAIL' if required else 'WARN'), 'detail': detail}


def check_postgres(env: dict[str, str]) -> dict:
    url = env.get('DATABASE_URL', '')
    if not url:
        return result('postgres', False, 'DATABASE_URL missing')
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(url, pool_pre_ping=True, connect_args={'connect_timeout': 8} if url.startswith('postgres') else {})
        with engine.connect() as c:
            one = c.execute(text('select 1')).scalar()
            tables = c.execute(text("select count(*) from information_schema.tables where table_schema='public'")).scalar()
        engine.dispose()
        return result('postgres', one == 1 and int(tables or 0) > 0, f'connectivity ok; public tables={int(tables or 0)}')
    except Exception as exc:
        return result('postgres', False, f'{type(exc).__name__}: connectivity/schema check failed')


def check_redis(env: dict[str, str]) -> dict:
    url = env.get('REDIS_URL', '')
    if not url:
        return result('redis', False, 'REDIS_URL missing')
    try:
        import redis
        r = redis.Redis.from_url(url, socket_connect_timeout=6, socket_timeout=6, decode_responses=True)
        pong = r.ping()
        return result('redis', pong is True, 'PING ok')
    except Exception as exc:
        return result('redis', False, f'{type(exc).__name__}: PING failed')


def r2_client(env: dict[str, str]):
    import boto3
    return boto3.client(
        's3', endpoint_url=env.get('S3_ENDPOINT_URL'), region_name=env.get('S3_REGION', 'auto'),
        aws_access_key_id=env.get('S3_ACCESS_KEY_ID'), aws_secret_access_key=env.get('S3_SECRET_ACCESS_KEY'),
    )


def check_r2(env: dict[str, str], write_canary: bool) -> dict:
    required = ['S3_ENDPOINT_URL','S3_BUCKET','S3_ACCESS_KEY_ID','S3_SECRET_ACCESS_KEY']
    if any(not env.get(k) for k in required):
        return result('r2', False, 'R2/S3 configuration incomplete')
    try:
        c = r2_client(env); bucket = env['S3_BUCKET']
        c.head_bucket(Bucket=bucket)
        if not write_canary:
            return result('r2', True, 'bucket access ok (read-only validation)')
        key = f'_v82_canary/{uuid.uuid4().hex}.txt'; body = b'mostashar-v82-canary'
        c.put_object(Bucket=bucket, Key=key, Body=body, ContentType='text/plain')
        got = c.get_object(Bucket=bucket, Key=key)['Body'].read()
        c.delete_object(Bucket=bucket, Key=key)
        return result('r2', got == body, 'bucket read/write/delete canary ok')
    except Exception as exc:
        return result('r2', False, f'{type(exc).__name__}: bucket validation failed')


def check_stream(env: dict[str, str]) -> dict:
    account = env.get('CF_ACCOUNT_ID',''); token = env.get('CF_STREAM_API_TOKEN','')
    if not account or not token:
        return result('cloudflare_stream', False, 'CF_ACCOUNT_ID/CF_STREAM_API_TOKEN missing')
    try:
        import httpx
        url = f'https://api.cloudflare.com/client/v4/accounts/{account}/stream'
        with httpx.Client(timeout=12.0) as client:
            r = client.get(url, headers={'Authorization': f'Bearer {token}'}, params={'per_page': 1})
        if r.status_code != 200:
            return result('cloudflare_stream', False, f'Cloudflare API returned HTTP {r.status_code}')
        data = r.json()
        return result('cloudflare_stream', bool(data.get('success')), 'Stream API authentication/library access ok')
    except Exception as exc:
        return result('cloudflare_stream', False, f'{type(exc).__name__}: Stream API validation failed')


def check_paymob(env: dict[str, str]) -> dict:
    keys = ['PAYMOB_SECRET_KEY','PAYMOB_PUBLIC_KEY','PAYMOB_HMAC_SECRET','PAYMOB_INTEGRATION_ID']
    configured = [bool(env.get(k)) for k in keys]
    if not any(configured):
        return result('paymob', False, 'Paymob not configured', required=False)
    if not all(configured):
        missing = ','.join(k for k in keys if not env.get(k))
        return result('paymob', False, f'incomplete configuration: {missing}')
    base = env.get('PAYMOB_BASE_URL','https://accept.paymob.com')
    if not base.startswith('https://'):
        return result('paymob', False, 'PAYMOB_BASE_URL must use HTTPS')
    if not str(env.get('PAYMOB_INTEGRATION_ID','')).isdigit():
        return result('paymob', False, 'PAYMOB_INTEGRATION_ID must be numeric')
    return result('paymob', True, 'credential set structurally complete; live payment requires synthetic acceptance transaction')


def check_public_urls(env: dict[str, str]) -> list[dict]:
    out=[]
    for key in ('PUBLIC_BASE_URL','FRONTEND_PRIMARY_ORIGIN'):
        val=env.get(key,'')
        ok=val.startswith('https://') and bool(urlparse(val).hostname)
        out.append(result(key.lower(), ok, 'HTTPS URL configured' if ok else 'missing/invalid HTTPS URL'))
    return out


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument('--env-file', type=Path)
    ap.add_argument('--label', default='environment')
    ap.add_argument('--write-canary', action='store_true', help='perform R2 put/get/delete canary')
    ap.add_argument('--json-report', type=Path)
    args=ap.parse_args()
    env=parse_env(args.env_file)
    checks=[]
    checks += check_public_urls(env)
    checks += [check_postgres(env), check_redis(env), check_r2(env,args.write_canary), check_stream(env), check_paymob(env)]
    failed=[x for x in checks if x['status']=='FAIL']
    print(f'V82 INFRASTRUCTURE VALIDATION — {args.label}')
    for x in checks: print(f"[{x['status']}] {x['check']}: {x['detail']}")
    summary={'label':args.label,'timestamp':int(time.time()),'checks':checks,'go':not failed}
    if args.json_report:
        args.json_report.write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
    print('GO' if not failed else 'NO-GO')
    return 0 if not failed else 1

if __name__=='__main__':
    raise SystemExit(main())
