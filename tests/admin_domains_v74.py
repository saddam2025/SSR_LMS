from pathlib import Path
from fastapi.routing import APIRoute
from app.main import app

main = Path('app/main.py').read_text(encoding='utf-8')
assert '@app.get("/admin/users"' not in main
assert '@app.get("/admin/students"' not in main
assert '@app.get("/admin/security"' not in main
assert '@app.get("/parent"' not in main
assert '@app.post("/admin/parents/link"' not in main

routes = []
for route in app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods or []:
            if method not in {'HEAD', 'OPTIONS'}:
                routes.append((method, route.path))
assert len(routes) == len(set(routes)), 'duplicate HTTP routes detected'
required = {
    ('GET','/admin/users'), ('POST','/admin/users'),
    ('GET','/admin/students'), ('POST','/admin/students/import'),
    ('POST','/admin/students/bulk'), ('GET','/admin/students/{student_id}'),
    ('GET','/admin/security'), ('POST','/admin/security/device/{device_id}/toggle'),
    ('POST','/admin/security/session/{session_id}/revoke'),
    ('GET','/parent'), ('POST','/admin/parents/link'),
}
missing = required - set(routes)
assert not missing, f'missing routes: {sorted(missing)}'
print('ADMIN DOMAINS V74 OK')
