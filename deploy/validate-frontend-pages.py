from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
F=ROOT/'frontend'
required=['student/index.html','student/course.html','student/lesson.html','student/learning.html','student/quiz.html','student/homework.html','assets/app.js','assets/style.css','config.js','_headers','_redirects']
missing=[x for x in required if not (F/x).is_file()]
if missing:
    raise SystemExit('FRONTEND PAGES CHECK FAILED: missing '+', '.join(missing))
config=(F/'config.js').read_text(encoding='utf-8')
if 'https://api.ragab-seddik.com' not in config:
    raise SystemExit('FRONTEND PAGES CHECK FAILED: production API_BASE mismatch')
headers=(F/'_headers').read_text(encoding='utf-8')
for needle in ['Content-Security-Policy:', 'X-Content-Type-Options: nosniff', 'https://api.ragab-seddik.com']:
    if needle not in headers:
        raise SystemExit('FRONTEND PAGES CHECK FAILED: missing '+needle)
js=(F/'assets/app.js').read_text(encoding='utf-8')
if 'credentials: "include"' not in js or 'localStorage' in js:
    raise SystemExit('FRONTEND PAGES CHECK FAILED: session handling policy regression')
print('V81 FRONTEND PAGES CHECK OK')
