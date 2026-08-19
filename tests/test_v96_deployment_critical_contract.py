from pathlib import Path
from starlette.requests import Request


def test_docker_healthcheck_follows_railway_port():
    docker = Path('Dockerfile').read_text(encoding='utf-8')
    assert "os.getenv('PORT','8000')" in docker
    assert "127.0.0.1:8000/ready" not in docker


def test_default_frontend_is_single_domain_same_origin():
    config = Path('frontend/config.js').read_text(encoding='utf-8')
    env = Path('.env.railway.example').read_text(encoding='utf-8')
    assert 'window.location.origin' in config
    assert 'https://api.ragab-seddik.com' not in config
    assert 'SEPARATED_FRONTEND_ENABLED=false' in env
    assert 'PUBLIC_BASE_URL=https://ragab-seddik.com' in env


def _request(headers):
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    return Request({'type':'http','method':'GET','path':'/','headers':raw,'client':('10.0.0.1', 1234),'scheme':'https','server':('test',443)})


def test_cloudflare_client_ip_precedes_railway_proxy_headers(monkeypatch):
    monkeypatch.setenv('TRUST_PROXY_HEADERS','true')
    monkeypatch.setenv('CLOUDFLARE_DEPLOYMENT','true')
    from app.request_context import client_ip
    req = _request({'cf-connecting-ip':'203.0.113.9','x-real-ip':'198.51.100.2','x-forwarded-for':'192.0.2.1'})
    assert client_ip(req) == '203.0.113.9'


def test_invalid_proxy_ip_is_never_trusted(monkeypatch):
    monkeypatch.setenv('TRUST_PROXY_HEADERS','true')
    monkeypatch.setenv('CLOUDFLARE_DEPLOYMENT','true')
    from app.request_context import client_ip
    req = _request({'cf-connecting-ip':'not-an-ip\ninjected','x-real-ip':'198.51.100.7'})
    assert client_ip(req) == '198.51.100.7'
