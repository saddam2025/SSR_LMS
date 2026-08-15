import os
os.environ.setdefault('ENV', 'test')
os.environ.setdefault('APP_SECRET', 'test-secret-change-this')

from fastapi.testclient import TestClient
from app.main import app


def route_modules():
    rows = {}
    for route in app.routes:
        path = getattr(route, 'path', None)
        endpoint = getattr(route, 'endpoint', None)
        if path and endpoint:
            rows.setdefault(path, set()).add(endpoint.__module__)
    return rows


def main():
    routes = route_modules()
    expected = {
        '/health': 'app.routers.system',
        '/ready': 'app.routers.system',
        '/internal/metrics': 'app.routers.system',
        '/app-version.json': 'app.routers.pwa',
        '/manifest.webmanifest': 'app.routers.pwa',
        '/sw.js': 'app.routers.pwa',
        '/support': 'app.routers.support',
        '/support/tickets': 'app.routers.support',
        '/support/tickets/{ticket_id}': 'app.routers.support',
        '/support/tickets/{ticket_id}/reply': 'app.routers.support',
        '/support/tickets/{ticket_id}/status': 'app.routers.support',
    }
    for path, module in expected.items():
        assert path in routes, f'missing route: {path}'
        assert module in routes[path], f'{path} not owned by {module}: {routes[path]}'

    # No migrated route should still be implemented by app.main.
    for path in expected:
        assert 'app.main' not in routes[path], f'duplicate legacy route remained: {path}'

    client = TestClient(app)
    health = client.get('/health')
    assert health.status_code == 200 and health.json().get('status') == 'ok'
    # Browser support center remains protected and redirects unauthenticated users through
    # the existing HTTP exception handler instead of exposing content.
    support = client.get('/support', follow_redirects=False)
    assert support.status_code in {302, 303, 307} and support.headers.get('location', '').startswith('/login')

    print('V64 BACKEND MODULARIZATION: PASS')


if __name__ == '__main__':
    main()
