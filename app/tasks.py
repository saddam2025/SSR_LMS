"""Reliable Redis-backed background task queue.

Redis Streams are used instead of BLPOP so a worker crash does not silently lose
an in-flight job. Messages are acknowledged only after the handler succeeds;
stale pending messages are reclaimed and retried by another worker.
"""
from __future__ import annotations

import json
import logging
import os
import socket
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from .cache import client as redis_client

logger = logging.getLogger("lms.tasks")

STREAM_KEY = os.getenv("TASK_STREAM_KEY", "lms:tasks:v2")
DEAD_STREAM_KEY = os.getenv("TASK_DEAD_STREAM_KEY", "lms:tasks:dead:v2")
GROUP_NAME = os.getenv("TASK_GROUP_NAME", "lms-workers-v2")
MAX_ATTEMPTS = max(1, min(int(os.getenv("TASK_MAX_ATTEMPTS", "3")), 10))
CLAIM_IDLE_MS = max(15_000, min(int(os.getenv("TASK_CLAIM_IDLE_MS", "60000")), 900_000))
STREAM_MAXLEN = max(1_000, min(int(os.getenv("TASK_STREAM_MAXLEN", "100000")), 1_000_000))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _job(name: str, payload: dict, *, attempts: int = 0, job_id: str | None = None) -> dict:
    return {
        "id": job_id or uuid.uuid4().hex,
        "name": str(name),
        "payload": payload or {},
        "attempts": int(attempts),
        "queued_at": _utc_now(),
    }


def enqueue(name: str, payload: dict) -> bool:
    """Enqueue one task. Returns False when Redis is temporarily unavailable.

    A dropped job here is otherwise silent (only communication_delivery has a
    DB-backed recovery path via worker._recover_queued_deliveries). Logging the
    failure gives operators a chance to notice and manually replay instead of
    quietly losing jobs during a Redis blip.
    """
    c = redis_client()
    if c is None:
        logger.warning("task_enqueue_dropped name=%s reason=redis_unavailable", name)
        return False
    job = _job(name, payload)
    try:
        c.xadd(STREAM_KEY, {"job": json.dumps(job, ensure_ascii=False)}, maxlen=STREAM_MAXLEN, approximate=True)
        return True
    except Exception:
        logger.exception("task_enqueue_failed name=%s job_id=%s", name, job.get("id"))
        return False


def enqueue_many(name: str, payloads: list[dict]) -> int:
    """Pipeline task creation so a large campaign does not perform one RTT per recipient."""
    if not payloads:
        return 0
    c = redis_client()
    if c is None:
        logger.warning("task_enqueue_many_dropped name=%s count=%d reason=redis_unavailable", name, len(payloads))
        return 0
    try:
        pipe = c.pipeline(transaction=False)
        for payload in payloads:
            job = _job(name, payload)
            pipe.xadd(STREAM_KEY, {"job": json.dumps(job, ensure_ascii=False)}, maxlen=STREAM_MAXLEN, approximate=True)
        result = pipe.execute()
        return len(result)
    except Exception:
        logger.exception("task_enqueue_many_failed name=%s count=%d", name, len(payloads))
        return 0


def _ensure_group(c) -> None:
    try:
        c.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
    except Exception as exc:
        # BUSYGROUP means another process already created the consumer group.
        if "BUSYGROUP" not in str(exc).upper():
            raise


def _dead_letter(c, raw: str, error: str, job: dict | None = None) -> None:
    payload = {
        "raw": raw[:20_000],
        "error": str(error)[:2_000],
        "failed_at": _utc_now(),
        "job_id": (job or {}).get("id", ""),
        "name": (job or {}).get("name", ""),
    }
    c.xadd(DEAD_STREAM_KEY, {"job": json.dumps(payload, ensure_ascii=False)}, maxlen=10_000, approximate=True)


def _process_message(c, message_id: str, fields: dict, handlers: dict[str, Callable[[dict], None]]) -> None:
    raw = fields.get("job", "") if isinstance(fields, dict) else ""
    job = None
    try:
        job = json.loads(raw)
        if not isinstance(job, dict):
            raise ValueError("task payload is not an object")
        name = str(job.get("name", ""))
        handler = handlers.get(name)
        if handler is None:
            raise RuntimeError(f"unknown task: {name}")
        handler(job.get("payload") or {})
        # Ack only after successful processing. XDEL keeps this single-group stream bounded.
        c.xack(STREAM_KEY, GROUP_NAME, message_id)
        c.xdel(STREAM_KEY, message_id)
    except Exception as exc:
        attempts = int((job or {}).get("attempts", 0)) + 1
        # Ack the failed delivery before creating the retry; this avoids one pending
        # message and one retry copy representing the same logical task.
        try:
            c.xack(STREAM_KEY, GROUP_NAME, message_id)
            c.xdel(STREAM_KEY, message_id)
        except Exception:
            pass
        if job and attempts < MAX_ATTEMPTS:
            retry = _job(
                str(job.get("name", "")),
                job.get("payload") or {},
                attempts=attempts,
                job_id=str(job.get("id", "")) or None,
            )
            retry["last_error"] = str(exc)[:1_000]
            c.xadd(STREAM_KEY, {"job": json.dumps(retry, ensure_ascii=False)}, maxlen=STREAM_MAXLEN, approximate=True)
        else:
            _dead_letter(c, raw, str(exc), job)


def _claim_stale(c, consumer: str, handlers: dict[str, Callable[[dict], None]]) -> int:
    """Recover jobs abandoned by a crashed worker (Redis 6.2+ XAUTOCLAIM)."""
    try:
        result = c.xautoclaim(STREAM_KEY, GROUP_NAME, consumer, CLAIM_IDLE_MS, "0-0", count=20)
    except Exception:
        return 0
    # redis-py returns (next_id, messages[, deleted_ids]) depending on server/client.
    messages = result[1] if isinstance(result, (tuple, list)) and len(result) >= 2 else []
    for message_id, fields in messages:
        _process_message(c, message_id, fields, handlers)
    return len(messages)


def run_worker(handlers: dict[str, Callable[[dict], None]], *, stop_event: threading.Event | None = None, consumer: str | None = None) -> None:
    """Run a bounded, crash-recoverable task consumer.

    Multiple web processes may run this worker safely: the Redis consumer group
    distributes each message to one consumer and stale pending messages are reclaimed.
    """
    stop_event = stop_event or threading.Event()
    consumer = consumer or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    last_claim = 0.0
    while not stop_event.is_set():
        c = redis_client()
        if c is None:
            stop_event.wait(1.0)
            continue
        try:
            _ensure_group(c)
            now = time.monotonic()
            if now - last_claim >= 30:
                _claim_stale(c, consumer, handlers)
                last_claim = now
            rows = c.xreadgroup(GROUP_NAME, consumer, {STREAM_KEY: ">"}, count=10, block=3000)
            for _stream, messages in rows or []:
                for message_id, fields in messages:
                    if stop_event.is_set():
                        return
                    _process_message(c, message_id, fields, handlers)
        except Exception:
            # Redis/network failure is retried; no local fallback is allowed because
            # it would reintroduce per-process task races in production.
            stop_event.wait(1.0)