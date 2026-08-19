import importlib
import threading
import time


def test_watermark_capacity_is_bounded(monkeypatch):
    monkeypatch.setenv("WATERMARK_MAX_CONCURRENT", "1")
    monkeypatch.setenv("WATERMARK_ACQUIRE_TIMEOUT_SECONDS", "1")
    import app.watermark as wm
    wm = importlib.reload(wm)
    entered = threading.Event()
    release = threading.Event()

    def holder():
        with wm.watermark_capacity():
            entered.set()
            release.wait(3)

    t = threading.Thread(target=holder)
    t.start()
    assert entered.wait(1)
    started = time.monotonic()
    try:
        with wm.watermark_capacity():
            assert False, "second watermark operation must not enter"
    except wm.WatermarkCapacityExceeded:
        pass
    assert time.monotonic() - started >= 0.8
    release.set(); t.join(2)
    assert not t.is_alive()
