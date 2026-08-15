import json
import os
import time
from typing import Any

try:
    import redis
except Exception:
    redis = None

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"
_RETRY_SECONDS = max(1, min(int(os.getenv("REDIS_RETRY_SECONDS", "5")), 60))
_client = None
_last_failure = 0.0
_local = {}


def client():
    global _client, _last_failure
    if not redis or not _REDIS_URL:
        return None
    if _client not in (None, False):
        return _client
    if _client is False and (time.time() - _last_failure) < _RETRY_SECONDS:
        return None
    try:
        candidate = redis.Redis.from_url(
            _REDIS_URL,
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
            health_check_interval=30,
        )
        candidate.ping()
        _client = candidate
        return _client
    except Exception:
        _client = False
        _last_failure = time.time()
        return None


def _local_allowed() -> bool:
    # Never pretend a process-local cache is equivalent to Redis in production.
    return not (_IS_PRODUCTION and _REDIS_URL)


def get_json(key: str):
    c = client()
    if c:
        raw = c.get(key)
        return json.loads(raw) if raw else None
    if not _local_allowed():
        return None
    item = _local.get(key)
    if not item:
        return None
    exp, val = item
    if exp < time.time():
        _local.pop(key, None)
        return None
    return val


def set_json(key: str, value: Any, ttl: int = 60):
    c = client()
    if c:
        c.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    elif _local_allowed():
        _local[key] = (time.time() + ttl, value)


def delete(key: str):
    c = client()
    if c:
        c.delete(key)
    _local.pop(key, None)
