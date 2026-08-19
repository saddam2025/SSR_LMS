from pathlib import Path

def test_docker_healthcheck_follows_railway_port_and_allowed_host():
    text = Path("Dockerfile").read_text(encoding="utf-8")
    assert "os.getenv('PORT','8000')" in text
    assert "/ready" in text
    assert "healthcheck.railway.app" in text
    assert "127.0.0.1:8000/" not in text
