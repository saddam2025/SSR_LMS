import re
from app.services import reports as service_reports
from app.routers import reports as reports_router

def test_reports_route_declares_bounded_page_size():
    src = open('app/routers/reports.py', encoding='utf-8').read()
    assert "page_size: int=100" in src
    assert "min(int(page_size or 100),200)" in src
    assert "visible_rows=rows[start:start+page_size]" in src

def test_reports_template_has_pagination_controls():
    html = open('app/templates/admin_reports.html', encoding='utf-8').read()
    assert 'صفحة {{page}} من {{total_pages}}' in html
    assert 'page={{page+1}}' in html
    assert 'page={{page-1}}' in html
