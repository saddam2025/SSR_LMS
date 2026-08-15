import json
import logging
import os
import secrets
import threading
import time
from collections import Counter
from fastapi import Request

_lock = threading.Lock()
_counters = Counter()
_latency_ms = Counter()


def configure_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def request_id(request: Request) -> str:
    existing = (request.headers.get("x-request-id") or "").strip()
    if existing and len(existing) <= 80 and all(ch.isalnum() or ch in "-_." for ch in existing):
        return existing
    return secrets.token_hex(12)


async def metrics_middleware(request: Request, call_next):
    rid = request_id(request)
    request.state.request_id = rid
    started = time.perf_counter()
    status = 500
    response = None
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        elapsed = (time.perf_counter() - started) * 1000
        route = request.scope.get("route")
        route_path = getattr(route, "path", None) or request.url.path
        key = f"{request.method} {route_path} {status}"
        with _lock:
            _counters[key] += 1
            _latency_ms[key] += int(elapsed)
        logging.getLogger("lms.request").info(
            json.dumps({
                "request_id": rid,
                "method": request.method,
                "route": route_path,
                "status": status,
                "duration_ms": round(elapsed, 2),
            }, ensure_ascii=False)
        )


def snapshot():
    with _lock:
        rows = []
        for key, count in _counters.items():
            rows.append({"route": key, "count": count, "avg_ms": round(_latency_ms[key] / max(count, 1), 2)})
        return sorted(rows, key=lambda x: x["count"], reverse=True)[:200]
