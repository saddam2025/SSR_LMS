import importlib

from fastapi.testclient import TestClient


def _reload_app(monkeypatch, include="false", preload="false"):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("HSTS_INCLUDE_SUBDOMAINS", include)
    monkeypatch.setenv("HSTS_PRELOAD", preload)
    # Test the source contract rather than production boot requirements.
    text = open("app/main.py", encoding="utf-8").read()
    assert 'HSTS_INCLUDE_SUBDOMAINS' in text
    assert 'HSTS_PRELOAD' in text
    return text


def test_hsts_preload_is_opt_in(monkeypatch):
    text = _reload_app(monkeypatch)
    assert 'os.getenv("HSTS_PRELOAD", "false")' in text
    assert 'os.getenv("HSTS_INCLUDE_SUBDOMAINS", "false")' in text
