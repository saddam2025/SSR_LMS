from pathlib import Path


def test_railway_healthcheck_uses_liveness_endpoint_and_300s_timeout():
    text = Path("railway.toml").read_text(encoding="utf-8")
    assert 'healthcheckPath = "/ready"' in text
    assert 'healthcheckTimeout = 300' in text


def test_container_binds_to_railway_port():
    start = Path("container-start.sh").read_text(encoding="utf-8")
    assert "--host 0.0.0.0" in start
    assert '--port "${PORT:-8000}"' in start


def test_health_endpoint_is_dependency_free_but_ready_is_deep():
    text = Path("app/routers/system.py").read_text(encoding="utf-8")
    health_body = text.split('@router.get("/health")',1)[1].split('@router.get("/ready")',1)[0]
    ready_body = text.split('@router.get("/ready")',1)[1]
    assert "SELECT 1" not in health_body
    assert "cache_client" not in health_body
    assert 'SELECT 1' in ready_body


def test_storage_roundtrip_does_not_block_startup_by_default():
    text = Path("app/preflight.py").read_text(encoding="utf-8")
    assert 'STORAGE_PREFLIGHT_ROUNDTRIP", "false"' in text
    assert 'PREFLIGHT_RETRIES' in text
