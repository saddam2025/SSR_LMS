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
_local: dict[str, tuple[float, Any]] = {}
_last_sweep = 0.0
_SWEEP_INTERVAL = 300  # seconds
_LOCAL_MAX_ENTRIES = max(500, min(int(os.getenv("LOCAL_CACHE_MAX_ENTRIES", "5000")), 100_000))


def _sweep_local():
    """Drop expired entries so the process-local fallback cache can't grow forever.

    Entries only used to expire lazily on read of that exact key, so a key that's
    written once and never read again (or a low-traffic dev/staging box with no
    Redis) would leak memory indefinitely. This runs opportunistically, at most
    every _SWEEP_INTERVAL seconds, from the existing get/set call sites -- no
    background thread needed.
    """
    global _last_sweep
    now = time.time()
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    expired = [k for k, (exp, _v) in _local.items() if exp < now]
    for k in expired:
        _local.pop(k, None)
    # Hard cap as a backstop even if TTLs are set very long: drop oldest-expiring first.
    if len(_local) > _LOCAL_MAX_ENTRIES:
        overflow = sorted(_local.items(), key=lambda kv: kv[1][0])[: len(_local) - _LOCAL_MAX_ENTRIES]
        for k, _ in overflow:
            _local.pop(k, None)


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
        _sweep_local()
        _local[key] = (time.time() + ttl, value)


def delete(key: str):
    c = client()
    if c:
        c.delete(key)
    _local.pop(key, None)


def delete_many(keys):
    keys = [str(k) for k in keys if k]
    if not keys:
        return
    c = client()
    if c:
        try:
            c.delete(*keys)
        except Exception:
            pass
    for key in keys:
        _local.pop(key, None)