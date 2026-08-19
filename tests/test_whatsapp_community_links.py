from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / "app" / "templates" / "home.html"
BASE = ROOT / "app" / "templates" / "base.html"
EXPECTED = {
    "الصف الأول الثانوي": "https://chat.whatsapp.com/CVTAGolYyuS0lzuGur3FAP",
    "الصف الثاني الثانوي عام": "https://chat.whatsapp.com/CsyWqET6j686jgQgN9FDY0",
    "الصف الثاني بكالوريا": "https://chat.whatsapp.com/J704OEHi47yA6SKKMqjufn?s=cl&p=a&ilr=1",
    "الصف الثالث الثانوي": "https://chat.whatsapp.com/F49VBaXN1wyCQQZJcslJZd",
}


def _community_home_links():
    text = HOME.read_text(encoding="utf-8")
    match = re.search(r'<section class="grade-community" id="community"[^>]*>(.*?)</section>', text, re.S)
    assert match, "Community section is missing"
    section = html.unescape(match.group(1))
    pairs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>\s*<b>([^<]+)</b>', section)
    return {label.strip(): href.strip() for href, label in pairs}


def _footer_links():
    text = html.unescape(BASE.read_text(encoding="utf-8"))
    match = re.search(r'<div class="official-community">(.*?)</div>', text, re.S)
    assert match, "Footer community block is missing"
    block = match.group(1)
    pairs = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>جروب\s+([^<]+)</a>', block)
    return {label.strip(): href.strip() for href, label in pairs}


def test_home_community_has_exact_whatsapp_links():
    assert _community_home_links() == EXPECTED


def test_footer_community_has_exact_whatsapp_links():
    assert _footer_links() == EXPECTED


def test_home_and_footer_communities_are_identical():
    assert _community_home_links() == _footer_links() == EXPECTED


def test_no_other_group_invites_in_home_or_footer():
    home_urls = re.findall(r'https://chat\.whatsapp\.com/[^"\s<]+', html.unescape(HOME.read_text(encoding="utf-8")))
    footer_match = re.search(r'<div class="official-community">(.*?)</div>', html.unescape(BASE.read_text(encoding="utf-8")), re.S)
    assert footer_match
    footer_urls = re.findall(r'https://chat\.whatsapp\.com/[^"\s<]+', footer_match.group(1))
    assert sorted(home_urls) == sorted(EXPECTED.values())
    assert sorted(footer_urls) == sorted(EXPECTED.values())
