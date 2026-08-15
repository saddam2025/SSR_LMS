from pathlib import Path
import importlib

router_text = Path('app/routers/learning_runtime.py').read_text()
assert 'getattr(_legacy' not in router_text, 'V70 broad getattr bridge must be removed'
for required in [
    'from ..db import engine, get_db',
    'from ..request_context import',
    'from ..services.learning_runtime import',
    'from ..security import',
]:
    assert required in router_text, required
# Only renderer/study intelligence + production compatibility may still use legacy bootstrap.
for forbidden in ['CheckpointAttempt = getattr', 'authorized_for_course = getattr', 'award_points = getattr', 'get_db = getattr']:
    assert forbidden not in router_text, forbidden

svc = importlib.import_module('app.services.learning_runtime')
for name in ['award_points','course_completion_status','issue_course_certificate','safe_range_header','validated_video_url','authorized_for_course','lesson_unlocked']:
    assert hasattr(svc, name), name

main_text = Path('app/main.py').read_text()
assert 'return runtime_course_completion_status' in main_text
assert 'return runtime_issue_course_certificate' in main_text
assert 'return runtime_award_points' in main_text
print('V71 LEARNING RUNTIME SERVICES: PASS')
