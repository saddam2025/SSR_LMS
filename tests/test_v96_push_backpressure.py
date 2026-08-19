from concurrent.futures import Future


def test_push_queue_is_bounded_and_non_blocking(monkeypatch):
    import app.push as push

    class FakeSlots:
        def __init__(self):
            self.calls = 0
            self.releases = 0
        def acquire(self, blocking=False):
            assert blocking is False
            self.calls += 1
            return self.calls == 1
        def release(self):
            self.releases += 1

    class FakeExecutor:
        def __init__(self):
            self.submits = 0
        def submit(self, fn, *args):
            self.submits += 1
            fut = Future()
            # Keep the future pending so the slot remains occupied for this test.
            return fut

    slots = FakeSlots()
    executor = FakeExecutor()
    monkeypatch.setattr(push, '_pending_slots', slots)
    monkeypatch.setattr(push, '_executor', executor)

    item = (1, 'title', 'body', '/notifications', 'info')
    assert push._submit_push(item) is True
    assert push._submit_push(item) is False
    assert executor.submits == 1


def test_push_submit_failure_releases_slot(monkeypatch):
    import app.push as push

    class FakeSlots:
        def __init__(self):
            self.releases = 0
        def acquire(self, blocking=False):
            return True
        def release(self):
            self.releases += 1

    class BrokenExecutor:
        def submit(self, fn, *args):
            raise RuntimeError('executor unavailable')

    slots = FakeSlots()
    monkeypatch.setattr(push, '_pending_slots', slots)
    monkeypatch.setattr(push, '_executor', BrokenExecutor())
    assert push._submit_push((1, 't', 'b', '/', 'info')) is False
    assert slots.releases == 1
