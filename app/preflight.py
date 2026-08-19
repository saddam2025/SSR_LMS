"""Railway pre-deploy preparation with stage-specific diagnostics.

Pre-deploy blocks only on production core configuration and PostgreSQL schema.
Redis/R2/Stream remain visible in production_status but cannot hide a valid web
release behind a generic pre-deploy failure. Railway /ready checks configured
Redis before traffic promotion.
"""
import os
import time

from .production import enforce_production_core, production_status


def _int_env(name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except Exception:
        value = default
    return max(lo, min(value, hi))


def _database_preflight() -> None:
    from sqlalchemy import inspect, text
    from .db import engine, ensure_schema
    from .schema_migrate import add_missing_columns_safely
    from .schema_guard import validate_schema, ensure_performance_indexes

    ensure_schema()
    migrated = add_missing_columns_safely()
    if migrated:
        print("MOSTASHAR PREDEPLOY MIGRATED: " + ", ".join(migrated), flush=True)
    validate_schema()
    ensure_performance_indexes()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _redis_advisory_check() -> None:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        print("MOSTASHAR PREDEPLOY WARNING: REDIS_URL not configured; web can boot but scale/queue guarantees are degraded", flush=True)
        return
    try:
        from .cache import client as cache_client
        c = cache_client()
        if not c or c.ping() is not True:
            raise RuntimeError("Redis ping failed")
        print("MOSTASHAR PREDEPLOY REDIS OK", flush=True)
    except Exception as exc:
        # /ready will keep traffic away while a configured Redis service is down.
        # Do not permanently fail a deployment because of a transient cache outage.
        print(f"MOSTASHAR PREDEPLOY WARNING: Redis unavailable: {type(exc).__name__}: {exc}", flush=True)


def run() -> None:
    print("MOSTASHAR PREDEPLOY STAGE 1/4: validating core Variables", flush=True)
    enforce_production_core()

    print("MOSTASHAR PREDEPLOY STAGE 2/4: preparing PostgreSQL schema", flush=True)
    attempts = _int_env("PREFLIGHT_RETRIES", 18, 1, 60)
    delay = _int_env("PREFLIGHT_RETRY_SECONDS", 3, 1, 15)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            _database_preflight()
            print(f"MOSTASHAR PREDEPLOY DATABASE OK attempt={attempt}", flush=True)
            break
        except Exception as exc:
            last_error = exc
            print(f"MOSTASHAR PREDEPLOY DB WAIT attempt={attempt}/{attempts}: {type(exc).__name__}: {exc}", flush=True)
            if attempt >= attempts:
                raise RuntimeError(f"PostgreSQL/schema pre-deploy failed after {attempts} attempts: {type(exc).__name__}: {exc}") from last_error
            time.sleep(delay)

    print("MOSTASHAR PREDEPLOY STAGE 3/4: checking Redis advisory state", flush=True)
    _redis_advisory_check()

    # Storage roundtrip stays explicit/opt-in because an external R2 outage must
    # not make a valid database migration impossible to deploy.
    if os.getenv("STORAGE_PREFLIGHT_ROUNDTRIP", "false").lower() in {"1", "true", "yes", "on"}:
        from .storage import mode as storage_mode, verify_storage_roundtrip
        if storage_mode() == "s3":
            verify_storage_roundtrip()
            print("MOSTASHAR PREDEPLOY STORAGE ROUNDTRIP OK", flush=True)

    status = production_status()
    missing_full = [k for k, v in status["required"].items() if not v]
    if missing_full:
        print("MOSTASHAR PREDEPLOY WARNING: full-launch integrations incomplete: " + ", ".join(missing_full), flush=True)

    print("MOSTASHAR PREDEPLOY STAGE 4/4: core preparation OK", flush=True)


if __name__ == "__main__":
    run()
