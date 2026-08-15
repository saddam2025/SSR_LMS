from collections import Counter
from app.main import app
import app.main as mainmod
from app.routers import courses as courses_router
from app.services import courses as courses_service

paths = {
    (r.path, tuple(sorted(getattr(r, 'methods', []) or [])), getattr(getattr(r, 'endpoint', None), '__module__', ''))
    for r in app.routes
}
expected = {
    ('/admin/courses', ('POST',)),
    ('/admin/course/{course_id}', ('GET',)),
    ('/admin/course/{course_id}/update', ('POST',)),
    ('/admin/course/{course_id}/lessons', ('POST',)),
    ('/admin/lesson/{lesson_id}/edit', ('GET',)),
    ('/admin/lesson/{lesson_id}/update', ('POST',)),
    ('/admin/lesson/{lesson_id}/drip-rule', ('POST',)),
    ('/admin/lesson/{lesson_id}/access-override', ('POST',)),
    ('/admin/lesson/{lesson_id}/video-profile', ('POST',)),
    ('/admin/lesson/{lesson_id}/move', ('POST',)),
    ('/admin/lesson/{lesson_id}/toggle', ('POST',)),
    ('/admin/lesson/{lesson_id}/delete', ('POST',)),
}
for path, methods in expected:
    matches = [r for r in app.routes if r.path == path and tuple(sorted(getattr(r, 'methods', []) or [])) == methods]
    assert len(matches) == 1, (path, methods, len(matches))
    assert matches[0].endpoint.__module__ == 'app.routers.courses', (path, matches[0].endpoint.__module__)

keys=[(r.path, tuple(sorted(getattr(r,'methods',[]) or []))) for r in app.routes]
assert not [k for k,v in Counter(keys).items() if v > 1]
assert mainmod.validated_video_url('') == ''
assert courses_service.validated_video_url('') == ''
assert courses_router.router.routes
print('V69 MODULAR COURSES/LESSONS ROUTER: PASS')
