import os
import re
from pathlib import Path

os.environ.setdefault('ENV', 'test')
os.environ.setdefault('APP_SECRET', 'test-secret-change-this')

ROOT = Path(__file__).resolve().parents[1]
base = (ROOT / 'app/templates/base.html').read_text(encoding='utf-8')
css = (ROOT / 'app/static/style.css').read_text(encoding='utf-8')

# Strict CSP in production blocks inline JS. Navigation must therefore be native HTML/CSS.
assert '<script>' not in base.lower(), 'Inline script found in base.html; strict CSP would block it'
assert 'class="mobile-menu"' in base and '<details class="mobile-menu">' in base
assert '<details class="nav-dropdown">' in base
assert 'desktop-nav' in css and 'mobile-menu-panel' in css

# V64 modular backend: collect routes from the FastAPI application itself rather than
# scraping decorators from main.py. This remains correct as routes move into APIRouters.
from app.main import app
routes = {getattr(route, 'path', '') for route in app.routes}
hrefs = set(re.findall(r'href="(/[^"]*)"', base))
for href in hrefs:
    path = href.split('#', 1)[0] or '/'
    if path.startswith('/static/'):
        continue
    assert path in routes or path == '/', f'Navigation href has no matching route: {href}'

print('NAVIGATION CONTRACT OK')
