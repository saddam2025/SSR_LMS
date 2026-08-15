import ast
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import hash_password
from app.seed import run

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'app' / 'templates'
APP_DIR = ROOT / 'app'

# 1) Every template rendered by Python exists.
template_files = {p.name for p in TEMPLATES.glob('*.html')}
route_names = set()
route_paths = []
for py in APP_DIR.rglob('*.py'):
    try:
        tree = ast.parse(py.read_text(encoding='utf-8'))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) and dec.func.attr in {'get','post','put','patch','delete','api_route'}:
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        route_names.add(node.name)
                        route_paths.append(dec.args[0].value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'render_template' and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                assert arg.value in template_files, f'Missing rendered template: {arg.value}'

# 2) Every literal href/form action maps to a declared route (or external/static URL).
def route_matches(path: str) -> bool:
    for pattern in route_paths:
        regex = '^' + re.sub(r'\{[^}]+\}', '[^/]+', pattern) + '$'
        if re.match(regex, path):
            return True
    return False

post_forms = 0
for tpl in TEMPLATES.glob('*.html'):
    text = tpl.read_text(encoding='utf-8')
    for endpoint in re.findall(r"url_for\(['\"]([^'\"]+)", text):
        assert endpoint in route_names, f'{tpl.name}: url_for target missing: {endpoint}'
    for value in re.findall(r'(?:href|action)=["\']([^"\']+)["\']', text):
        if '{{' in value or '{%' in value or not value.startswith('/'):
            continue
        path = value.split('?', 1)[0].split('#', 1)[0] or '/'
        if path.startswith('/static/') or path.startswith('/api/v1/'):
            continue
        assert route_matches(path), f'{tpl.name}: literal target has no route: {value}'
    for form in re.findall(r'<form\b[^>]*method=["\']post["\'][^>]*>.*?</form>', text, re.I | re.S):
        post_forms += 1
        assert re.search(r'name=["\']csrf["\']', form), f'{tpl.name}: POST form missing CSRF'
assert post_forms >= 100

# 3) Dynamic JS actions map to real route families.
admin_js = (APP_DIR / 'static' / 'admin-interactive.js').read_text(encoding='utf-8')
assert '/admin/lesson/${select.value}/${kind}' in admin_js
for suffix in ('checkpoints', 'flashcards'):
    assert f'/admin/lesson/{{lesson_id}}/{suffix}' in route_paths
lesson_js = (APP_DIR / 'static' / 'lesson-experience.js').read_text(encoding='utf-8')
assert '/api/mobile/offline/lesson/${offlineButton.dataset.lessonId}/grant' in lesson_js
assert '/api/mobile/offline/lesson/{lesson_id}/grant' in route_paths

# 4) Every staff role lands on a page it is authorized to use, and visible internal GET menu links never return 403/404/5xx.
run()
PASSWORD = 'RoleContract123!'
role_landing = {
    'content_manager': '/teacher',
    'support': '/support',
    'accounting': '/admin/commerce',
}
with SessionLocal() as db:
    for role in role_landing:
        email = f'contract-{role}@example.local'
        user = db.query(User).filter_by(email=email).first()
        if not user:
            db.add(User(name=f'Contract {role}', email=email, password_hash=hash_password(PASSWORD), role=role, is_active=True, mfa_enabled=True))
    db.commit()

for role, landing in role_landing.items():
    client = TestClient(app)
    login_page = client.get('/login')
    csrf = re.search(r'name="csrf" value="([^"]+)"', login_page.text).group(1)
    resp = client.post('/login', data={'email': f'contract-{role}@example.local', 'password': PASSWORD, 'csrf': csrf}, follow_redirects=False)
    assert resp.status_code == 303, (role, 'login', resp.status_code)
    dash = client.get('/dashboard', follow_redirects=False)
    assert dash.status_code in (302,303), (role, 'dashboard', dash.status_code)
    assert urlparse(dash.headers['location']).path == landing, (role, dash.headers['location'], landing)
    page = client.get(landing, follow_redirects=False)
    assert page.status_code == 200, (role, landing, page.status_code)
    hrefs = set(re.findall(r'href=["\']([^"\']+)["\']', page.text))
    for href in hrefs:
        if not href.startswith('/') or href.startswith('/static/') or '{' in href:
            continue
        path = urlparse(href).path
        if path in {'/logout'}:
            continue
        r = client.get(path, follow_redirects=False)
        assert r.status_code not in {403,404,500,502,503}, (role, path, r.status_code)

print(f'PAGE/TASK LINKAGE CONTRACT OK: {len(route_paths)} routes, {len(template_files)} templates, {post_forms} POST forms, staff role menus authorized')
