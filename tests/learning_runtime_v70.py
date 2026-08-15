from collections import Counter
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('ENV','test')
os.environ.setdefault('DATABASE_URL','sqlite://')
os.environ.setdefault('APP_SECRET','v70-'+'x'*96)
from app.main import app
import app.main as mainmod
from app.routers import learning_runtime

expected = {
    ('/course/{course_id}', ('GET',)),
    ('/lesson/{lesson_id}', ('GET',)),
    ('/lesson/{lesson_id}/assistant', ('POST',)),
    ('/lesson/{lesson_id}/checkpoint/{checkpoint_id}', ('POST',)),
    ('/api/mobile/offline/lesson/{lesson_id}/capability', ('GET',)),
    ('/api/mobile/offline/lesson/{lesson_id}/grant', ('POST',)),
    ('/protected/video/{lesson_id}', ('GET',)),
    ('/protected/lesson/{lesson_id}', ('GET',)),
    ('/api/lesson/{lesson_id}/progress', ('POST',)),
    ('/quiz/{quiz_id}', ('GET',)),
    ('/quiz/{quiz_id}', ('POST',)),
    ('/homework/{homework_id}', ('GET',)),
    ('/homework/{homework_id}', ('POST',)),
    ('/lesson/{lesson_id}/discussion', ('POST',)),
}
for path, methods in expected:
    matches=[r for r in app.routes if r.path==path and tuple(sorted(getattr(r,'methods',[]) or []))==methods]
    assert len(matches)==1, (path, methods, len(matches))
    assert matches[0].endpoint.__module__ == 'app.routers.learning_runtime', (path, matches[0].endpoint.__module__)
keys=[(r.path, tuple(sorted(getattr(r,'methods',[]) or []))) for r in app.routes]
assert not [k for k,v in Counter(keys).items() if v>1]
source=Path('app/main.py').read_text()
for marker in ['@app.get("/protected/video/{lesson_id}")','@app.post("/api/lesson/{lesson_id}/progress")','@app.get("/quiz/{quiz_id}"','@app.post("/quiz/{quiz_id}"','@app.get("/homework/{homework_id}"','@app.post("/homework/{homework_id}"']:
    assert marker not in source, marker
assert learning_runtime.router.routes
print('V70 STUDENT LEARNING RUNTIME ROUTER: PASS')
