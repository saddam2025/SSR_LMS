import inspect
from collections import Counter
from fastapi.routing import APIRoute

from app.main import app
import app.main as main_mod
import app.routers.homepage as homepage_router
import app.routers.academic_content as academic_router
import app.routers.remediation as remediation_router

source = inspect.getsource(main_mod)
for marker in [
    '@app.get("/",',
    '@app.get("/admin/homepage"',
    '@app.get("/teacher/content"',
    '@app.get("/teacher/revision"',
    '@app.get("/revision"',
    '@app.get("/smart-tutor"',
    '@app.get("/learning-plan"',
]:
    assert marker not in source, marker

assert '/admin/homepage' in inspect.getsource(homepage_router)
assert '/teacher/content' in inspect.getsource(academic_router)
assert '/teacher/revision' in inspect.getsource(academic_router)
assert '/revision' in inspect.getsource(academic_router)
assert '/smart-tutor' in inspect.getsource(remediation_router)
assert '/learning-plan' in inspect.getsource(remediation_router)

pairs=[]
for route in app.routes:
    if isinstance(route, APIRoute):
        for method in route.methods or []:
            if method not in {'HEAD','OPTIONS'}:
                pairs.append((method, route.path))
counts=Counter(pairs)
dupes={k:v for k,v in counts.items() if v > 1}
assert not dupes, dupes

required={
    ('GET','/'), ('GET','/admin/homepage'), ('GET','/teacher/content'),
    ('GET','/teacher/revision'), ('GET','/revision'), ('GET','/smart-tutor'),
    ('GET','/learning-plan'), ('GET','/admin/students/{student_id}/learning-plan'),
}
assert required.issubset(set(pairs)), required-set(pairs)
print('V76 ARCHITECTURE CLEANUP: PASS')
