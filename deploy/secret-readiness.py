#!/usr/bin/env python3
"""Validate deployment env files without printing secret values.

Safe to run locally against temporary env files. It reports only key names/status.
"""
from __future__ import annotations
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

PLACEHOLDER_PREFIXES=("REPLACE_","CHANGE_","CHANGEME","YOUR_","EXAMPLE_")
CORE_REQUIRED={
    "APP_SECRET","CF_EDGE_SIGNING_SECRET","CF_STREAM_CUSTOMER_CODE","CF_ACCOUNT_ID",
    "CF_STREAM_API_TOKEN","DATABASE_URL","REDIS_URL","ADMIN_EMAIL","ADMIN_PASSWORD",
    "S3_ENDPOINT_URL","S3_BUCKET","S3_ACCESS_KEY_ID","S3_SECRET_ACCESS_KEY",
}
PROVIDER_GROUPS={
    "paymob": {"PAYMOB_SECRET_KEY","PAYMOB_PUBLIC_KEY","PAYMOB_HMAC_SECRET","PAYMOB_INTEGRATION_ID"},
    "fcm": {"FIREBASE_PROJECT_ID","FIREBASE_SERVICE_ACCOUNT_JSON"},
    "otp_sms": {"OTP_SMS_WEBHOOK_URL","OTP_SMS_WEBHOOK_TOKEN"},
    "drm": {"DRM_PROVIDER","DRM_LICENSE_SERVER_URL"},
}


def parse_env(path: Path) -> dict[str,str]:
    out={}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1)
        out[k.strip()]=v.strip().strip('"').strip("'")
    return out


def present(v: str|None) -> bool:
    if not v: return False
    u=v.strip().upper()
    return not any(u.startswith(p) for p in PLACEHOLDER_PREFIXES)


def safe_host(v: str) -> str:
    try: return urlparse(v).hostname or ""
    except Exception: return ""


def validate(env: dict[str,str], label: str) -> list[str]:
    errors=[]
    missing=sorted(k for k in CORE_REQUIRED if not present(env.get(k)))
    if missing: errors.append(f"{label}: missing/placeholder core keys: {', '.join(missing)}")
    if present(env.get("APP_SECRET")) and len(env["APP_SECRET"]) < 64:
        errors.append(f"{label}: APP_SECRET must be at least 64 characters")
    if present(env.get("CF_EDGE_SIGNING_SECRET")) and len(env["CF_EDGE_SIGNING_SECRET"]) < 32:
        errors.append(f"{label}: CF_EDGE_SIGNING_SECRET must be at least 32 characters")
    if env.get("ENV","production").lower() != "production":
        errors.append(f"{label}: ENV must be production for deployed backend")
    if env.get("RUN_SEED_ON_START","false").lower() != "false":
        errors.append(f"{label}: RUN_SEED_ON_START must be false")
    if env.get("REQUIRE_STAFF_MFA","true").lower() != "true":
        errors.append(f"{label}: REQUIRE_STAFF_MFA must be true")
    if env.get("ALLOW_DIRECT_VIDEO_PROXY","false").lower() != "false":
        errors.append(f"{label}: ALLOW_DIRECT_VIDEO_PROXY must be false")
    for key in ("PUBLIC_BASE_URL", "S3_ENDPOINT_URL"):
        if present(env.get(key)) and not env[key].lower().startswith("https://"):
            errors.append(f"{label}: {key} must use HTTPS")
    if present(env.get("DATABASE_URL")) and not re.match(r"^postgres(?:ql)?(?:\+[^:]+)?://", env["DATABASE_URL"], re.I):
        errors.append(f"{label}: DATABASE_URL must be PostgreSQL")
    if present(env.get("REDIS_URL")) and not re.match(r"^rediss?://", env["REDIS_URL"], re.I):
        errors.append(f"{label}: REDIS_URL must be redis:// or rediss://")

    # Provider completeness: if any member is configured/enabled, require the full group.
    for name, keys in PROVIDER_GROUPS.items():
        enabled = any(present(env.get(k)) for k in keys)
        if name == "fcm": enabled = enabled or env.get("FCM_ENABLED","false").lower()=="true"
        if enabled:
            miss=sorted(k for k in keys if not present(env.get(k)))
            if miss: errors.append(f"{label}: {name} enabled but incomplete: {', '.join(miss)}")
    return errors


def compare(prod: dict[str,str], stage: dict[str,str]) -> list[str]:
    errors=[]
    for k in ("APP_SECRET","CF_EDGE_SIGNING_SECRET","DATABASE_URL","REDIS_URL","ADMIN_PASSWORD"):
        if present(prod.get(k)) and present(stage.get(k)) and prod[k] == stage[k]:
            errors.append(f"environment isolation: {k} must differ between production and staging")
    for k in ("PUBLIC_BASE_URL","FRONTEND_PRIMARY_ORIGIN"):
        if present(prod.get(k)) and present(stage.get(k)) and prod[k] == stage[k]:
            errors.append(f"environment isolation: {k} must differ between production and staging")
    # Warn/error if database or Redis hosts are identical; same managed provider host can still be safe,
    # but identical full URLs are already rejected above. Keep host check informational only.
    return errors


def main() -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--production", type=Path)
    p.add_argument("--staging", type=Path)
    args=p.parse_args()
    if not args.production and not args.staging:
        p.error("provide --production and/or --staging")
    all_errors=[]
    prod=stage=None
    if args.production:
        prod=parse_env(args.production); all_errors += validate(prod,"production")
    if args.staging:
        stage=parse_env(args.staging); all_errors += validate(stage,"staging")
    if prod is not None and stage is not None:
        all_errors += compare(prod,stage)
    if all_errors:
        print("SECRET READINESS: FAIL")
        for e in all_errors: print("-",e)
        return 1
    labels=[]
    if prod is not None: labels.append("production")
    if stage is not None: labels.append("staging")
    print("SECRET READINESS: PASS (values not displayed):", ", ".join(labels))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
