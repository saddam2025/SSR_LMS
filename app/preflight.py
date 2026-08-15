"""Production dependency preflight used by container-start.sh."""
import os
from sqlalchemy import text
from .cache import client as cache_client
from .db import engine
from .schema_guard import bootstrap_and_validate_schema
from .production import enforce_production_baseline, production_status


def run() -> None:
    enforce_production_baseline()
    bootstrap_and_validate_schema()
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    if os.getenv("REDIS_URL", "").strip():
        c = cache_client()
        if not c or not c.ping():
            raise RuntimeError("Redis preflight failed")
    status = production_status()
    if os.getenv("ENV", "development").lower() == "production" and not status["required_ok"]:
        raise RuntimeError("Production baseline is incomplete")
    print("MOSTASHAR PREFLIGHT OK")


if __name__ == "__main__":
    run()
