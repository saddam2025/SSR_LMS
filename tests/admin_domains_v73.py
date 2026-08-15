from app.main import app
from pathlib import Path

routes=[(tuple(sorted(getattr(r,'methods',[]) or [])), r.path) for r in app.routes if hasattr(r,'path') and hasattr(r,'methods')]
for path in ['/admin/communications','/admin/communications/send','/admin/communications/quick','/admin/reports','/admin/reports.xlsx','/admin/reports.pdf']:
    assert sum(1 for _,p in routes if p==path)==1, f'duplicate/missing route: {path}'
main=Path('app/main.py').read_text()
assert '@app.get("/admin/communications"' not in main
assert '@app.post("/admin/communications/send"' not in main
assert '@app.get("/admin/reports"' not in main
assert 'communications_router' in main and 'reports_router' in main
print('V73 ADMIN DOMAINS EXTRACTION: PASS')
