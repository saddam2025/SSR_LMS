from pathlib import Path
import html
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"
EXPECTED = [
    ("الصف الأول الثانوي", "https://chat.whatsapp.com/CVTAGolYyuS0lzuGur3FAP"),
    ("الصف الثاني الثانوي عام", "https://chat.whatsapp.com/CsyWqET6j686jgQgN9FDY0"),
    ("الصف الثاني بكالوريا", "https://chat.whatsapp.com/J704OEHi47yA6SKKMqjufn?s=cl&p=a&ilr=1"),
    ("الصف الثالث الثانوي", "https://chat.whatsapp.com/F49VBaXN1wyCQQZJcslJZd"),
]


def _render_home():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "xml"]))
    tpl = env.get_template("home.html")
    return html.unescape(tpl.render(
        request=None, user=None, csrf="", unread_notifications=0,
        staff_mfa_pending=False, role_labels={}, is_production=False,
        courses=[], reels=[], honors=[], reels_enabled=False, honors_enabled=False,
    ))


def test_rendered_home_has_four_visible_official_group_cards():
    rendered = _render_home()
    m = re.search(r'<section class="grade-community" id="community"[^>]*>(.*?)</section>', rendered, re.S)
    assert m, "rendered community section missing"
    block = m.group(1)
    cards = re.findall(r'<a\s+data-grade="[^"]+"\s+href="([^"]+)"[^>]*>\s*<b>([^<]+)</b>', block, re.S)
    actual = [(label.strip(), href.strip()) for href, label in cards]
    assert actual == EXPECTED
    assert 'data-community-count="4"' in block


def test_homepage_html_cache_is_disabled_for_operational_links():
    main = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert 'elif path == "/":' in main
    assert 'no-store, no-cache, max-age=0, must-revalidate' in main
