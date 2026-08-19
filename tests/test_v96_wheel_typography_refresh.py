from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_home_wheel_is_native_responsive_and_wired():
    home = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/sherif-inspired-v96.css").read_text(encoding="utf-8")

    assert 'class="mostashar-skill-wheel"' in home
    assert 'class="skill-wheel-center"' in home
    assert 'ragab-seddik-portrait-v94.webp' in home
    assert 'ragab-english-wheel-premium-2026.webp' not in home
    for href in (
        '/english-lab#flashcards',
        '/english-lab#tense-lab',
        '/english-lab#sentence-builder',
        '/english-lab#speaking',
    ):
        assert href in home
    for cls in ('node-vocab', 'node-tenses', 'node-grammar', 'node-speaking'):
        assert cls in home

    assert '.mostashar-skill-wheel{' in css
    assert 'aspect-ratio:1' in css
    assert '@media(max-width:620px)' in css
    assert '@media(max-width:390px)' in css
    assert '@media(prefers-reduced-motion:reduce)' in css


def test_typography_refresh_uses_arabic_and_english_font_stacks():
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")
    style = (ROOT / "app/static/style.css").read_text(encoding="utf-8")
    home_css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")

    assert 'family=Tajawal' in base
    assert 'family=Cairo' in base
    assert 'family=Montserrat' in base
    assert 'font-family:"Tajawal","Cairo"' in style
    assert 'body.home-v95{font-family:"Tajawal","Cairo"' in home_css
