from pathlib import Path
from fastapi.routing import APIRoute
from app.main import app

main = Path('app/main.py').read_text(encoding='utf-8')
for marker in [
    '@app.get("/admin/attendance"', '@app.get("/schedule"',
    '@app.get("/admin/live-classes"', '@app.get("/admin/groups"'
]:
    assert marker not in main, f'route still present in main.py: {marker}'

routes=[]
for route in app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods or []:
            if method not in {'HEAD','OPTIONS'}:
                routes.append((method, route.path))
assert len(routes)==len(set(routes)), 'duplicate HTTP routes detected'
required={
    ('GET','/admin/attendance'), ('POST','/admin/attendance/mark'),
    ('POST','/admin/attendance/notify-inactive'), ('GET','/schedule'),
    ('POST','/live-class/{class_id}/join'), ('GET','/admin/live-classes'),
    ('POST','/admin/live-classes/create'), ('GET','/admin/live-classes/{class_id}'),
    ('POST','/admin/live-classes/{class_id}/attendance'), ('GET','/admin/groups'),
    ('POST','/admin/groups/create'), ('GET','/admin/groups/{group_id}'),
    ('POST','/admin/groups/{group_id}/member'), ('POST','/admin/groups/{group_id}/course'),
    ('POST','/admin/groups/{group_id}/live-class'),
}
missing=required-set(routes)
assert not missing, f'missing routes: {sorted(missing)}'

community = Path('app/routers/community.py').read_text(encoding='utf-8')
service = Path('app/services/community.py').read_text(encoding='utf-8')
assert 'safe_live_url' in service and 'student_live_classes' in service
assert 'attendance_rows' in service and 'sync_group_course' in service
assert 'from ..services.community import' in community
print('COMMUNITY DOMAINS V75 OK')
