from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_homepage_mobile_menu_and_floating_actions_cannot_cover_controls():
    css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")
    assert '.mobile-menu:not([open]) > .mobile-menu-panel{display:none!important}' in css
    assert '@media (max-width:1199px)' in css
    assert '.home-ai-fab,' in css and '.whatsapp-float{display:none!important}' in css
    assert '@media (min-width:1200px)' in css
    assert 'width:48px!important;height:48px!important' in css


def test_mobile_comparison_stays_inside_its_scroll_frame():
    css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")
    assert 'body.home-v95 .mostashar-compare-wrap{width:100%;max-width:100%;direction:ltr}' in css
    assert 'body.home-v95 .mostashar-compare-table{direction:rtl}' in css


def test_redundant_hero_wheel_books_are_not_rendered():
    css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")
    assert 'body.home-v95 .v95-books,' in css
    assert 'body.home-v95 .v95-london-eye{display:none!important}' in css
