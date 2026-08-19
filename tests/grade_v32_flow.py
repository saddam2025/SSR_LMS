import os
import json
from pathlib import Path
os.environ.setdefault('ENV','development')
os.environ.setdefault('DATABASE_URL','sqlite:///./grade_v32_test.db')
from fastapi.testclient import TestClient
from app.main import app, GRADE_ORDER

assert GRADE_ORDER == [
    'الصف الأول الثانوي',
    'الصف الثاني الثانوي عام',
    'الصف الثاني بكالوريا',
    'الصف الثالث الثانوي',
]
with TestClient(app) as c:
    r=c.get('/')
    assert r.status_code == 200
    assert 'الصف الثاني الثانوي عام' in r.text
    assert 'الصف الثاني بكالوريا' in r.text
    v=c.get('/app-version.json')
    expected = json.loads(Path('app/static/app-version.json').read_text(encoding='utf-8'))['version']
    assert v.status_code == 200 and v.json()['version'] == expected
print('GRADE V32 + APP VERSION FLOW OK')
