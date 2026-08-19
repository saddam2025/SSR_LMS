from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sherif_public_parity_completion_contract():
    home = (ROOT / "app/templates/home.html").read_text()
    base = (ROOT / "app/templates/base.html").read_text()
    js = (ROOT / "app/static/sherif-home-tools.js").read_text()
    css = (ROOT / "app/static/sherif-inspired-v96.css").read_text()

    # Public learning features surfaced by the reference experience.
    for text in (
        "القاموس الناطق",
        "روتين 10-20-30",
        "خريطة ذهنية يومية",
        "بطاقات مراجعة",
        "مراجعة متباعدة",
        "مراجعة الصدى الصوتي",
        "الصناديق الذكية",
        "تحدي الدقيقة",
        "التعلّم بالنطق المباشر",
        "التحدي الثنائي الصوتي",
        "جدول المراجعة الأسبوعي",
        "القاموس الناطق الذهبي",
    ):
        assert text in home

    # Homepage discoverability and interaction parity.
    assert '/#speaking-dictionary' in base
    assert '/#student-reviews' in base
    assert 'data-course-filters' in home
    assert 'data-course-card' in home
    assert 'data-course-filter-status' in home
    assert "courseFilterRoot" in js
    assert "touchstart" in js and "ArrowRight" in js
    assert ".sherif-course-filters" in css
    assert "طلابنا <em>بيقولوا إيه</em>" in home
    # Current public-reference organization: golden ideas + continuous reviews.
    assert "أفكار ذهبية ومنظمة" in home
    assert "مراجعات دائمة ومستمرة" in home
    for word in ("Hello", "Beautiful", "Amazing", "Study", "Review", "Pronunciation", "Modern", "Simple", "Focus", "Success"):
        assert f'data-pronounce-word="{word}"' in home
    # Mobile filters must wrap rather than place tappable filters off-canvas.
    assert "Mobile course filters: keep every filter directly tappable" in css
    assert "flex-wrap:wrap" in css
