import json
from pathlib import Path


def test_task_queue_uses_redis_streams_and_ack_after_handler():
    code = Path("app/tasks.py").read_text(encoding="utf-8")
    assert "xreadgroup" in code
    assert "xautoclaim" in code
    assert "xack" in code
    assert ".blpop(" not in code.lower()
    assert "MAX_ATTEMPTS" in code


def test_external_communications_are_not_sent_inline_in_request_router():
    code = Path("app/routers/communications.py").read_text(encoding="utf-8")
    assert "send_message_webhook" not in code
    assert 'status = "queued" if configured else "not_configured"' in code
    assert 'if configured:' in code
    assert 'enqueue_many("communication_delivery"' in code


def test_worker_delivery_handler_is_idempotent_by_status():
    code = Path("app/worker.py").read_text(encoding="utf-8")
    assert 'delivery.status not in {"queued", "retry"}' in code
    assert "Idempotency" not in code  # header is set by service using supplied key
    assert 'idempotency_key=f"mostashar-communication-{delivery.id}"' in code


def test_failed_task_is_retried_then_dead_lettered(monkeypatch):
    import app.tasks as tasks

    class FakeRedis:
        def __init__(self):
            self.acks=[]; self.deletes=[]; self.adds=[]
        def xack(self,*args): self.acks.append(args)
        def xdel(self,*args): self.deletes.append(args)
        def xadd(self,*args,**kwargs): self.adds.append((args,kwargs)); return "2-0"

    c=FakeRedis()
    raw=json.dumps({"id":"abc","name":"boom","payload":{"x":1},"attempts":0})
    def boom(payload):
        raise RuntimeError("failed")
    tasks._process_message(c,"1-0",{"job":raw},{"boom":boom})
    assert c.acks
    assert c.deletes
    assert c.adds
    retry=json.loads(c.adds[0][0][1]["job"])
    assert retry["attempts"] == 1
    assert retry["id"] == "abc"
