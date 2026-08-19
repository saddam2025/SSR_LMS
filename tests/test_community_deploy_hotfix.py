from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
HOME = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
BASE = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
MAIN = (ROOT / "app/main.py").read_text(encoding="utf-8")
SW = (ROOT / "app/static/sw.js").read_text(encoding="utf-8")
VERSION_META = json.loads((ROOT / "app/static/app-version.json").read_text(encoding="utf-8"))

EXPECTED = {
    "first-secondary": "https://chat.whatsapp.com/CVTAGolYyuS0lzuGur3FAP",
    "second-secondary-general": "https://chat.whatsapp.com/CsyWqET6j686jgQgN9FDY0",
    "second-baccalaureate": "https://chat.whatsapp.com/J704OEHi47yA6SKKMqjufn?s=cl&amp;p=a&amp;ilr=1",
    "third-secondary": "https://chat.whatsapp.com/F49VBaXN1wyCQQZJcslJZd",
}

def test_four_groups_are_in_visible_home_section():
    start = HOME.index('<section class="grade-community"')
    end = HOME.index('</section>', start)
    block = HOME[start:end]
    assert 'data-community-count="4"' in block
    for grade, url in EXPECTED.items():
        assert f'data-grade="{grade}"' in block
        assert url in block
    assert block.count('target="_blank"') == 4

def test_footer_has_same_four_groups():
    for grade, url in EXPECTED.items():
        assert f'data-grade="{grade}"' in BASE
        assert url in BASE

def test_deployment_fingerprint_and_cache_bypass_present():
    import json
    release = json.loads(Path("app/static/app-version.json").read_text(encoding="utf-8"))["release"]
    assert release in BASE
    assert release in MAIN
    assert VERSION_META["release"] == release
    assert 'Cloudflare-CDN-Cache-Control"] = "no-store"' in MAIN
    assert "ragab-seddik-static-v96-wheel-typography1" in SW
