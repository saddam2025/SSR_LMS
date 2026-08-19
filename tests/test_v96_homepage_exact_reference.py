from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_v96_homepage_reference_contract():
    home = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")
    base = (ROOT / "app/templates/base.html").read_text(encoding="utf-8")

    # Approved reference content/elements stay present.
    for marker in (
        'class="v95-hero"',
        'class="v95-teacher-side"',
        'ragab-seddik-portrait-v94.webp',
        'class="v95-hero-copy"',
        'class="v95-hero-actions"',
        'class="v95-stats"',
        'class="v95-quote-band"',
        'class="v95-feature-ribbon"',
        'مستر رجب صديق',
        'Al-Mostashar in English',
    ):
        assert marker in home

    # Desktop fix: portrait and copy are forced into the same grid row.
    assert 'body.home-v95 .v95-hero-copy{' in css
    assert 'grid-column:1;' in css and 'grid-row:1;' in css
    assert 'body.home-v95 .v95-teacher-side{' in css
    assert 'grid-column:2;' in css

    # Responsive contracts used by the visual QA pass.
    assert '@media (min-width:901px) and (max-width:1200px)' in css
    assert '@media (max-width:900px)' in css
    assert '@media (max-width:620px)' in css
    assert 'grid-template-columns:1fr 1fr' in css
    assert 'pointer-events:none' in css

    # Typography/cache revision is explicit so Railway/CDN clients receive V96 CSS.
    assert 'family=Cairo' in base
    assert '20260818-wheel-typography-1' in base
    assert 'home-v96.css?v=20260818-wheel-typography-1' in home
