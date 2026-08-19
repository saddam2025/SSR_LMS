from pathlib import Path

def test_railway_healthcheck_host_is_trusted_in_production():
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert 'railway_health_host = "healthcheck.railway.app"' in main
    assert 'railway_health_host, *extra_hosts' in main
    env = Path(".env.railway.example").read_text(encoding="utf-8")
    assert "healthcheck.railway.app" in env
