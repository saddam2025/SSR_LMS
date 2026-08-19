from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_public_reference_system_contract_static():
    auth = (ROOT / "app/routers/auth.py").read_text()
    home_router = (ROOT / "app/routers/homepage.py").read_text()
    login = (ROOT / "app/templates/login.html").read_text()
    home = (ROOT / "app/templates/home.html").read_text()
    admin = (ROOT / "app/templates/admin_homepage.html").read_text()

    assert '@router.get("/Login"' in auth
    assert '@router.post("/Login"' in auth
    assert "رقم الهاتف" in login
    assert '@router.get("/Courses"' in home_router
    assert "القاموس الناطق" in home
    assert "خريطة ذهنية يومية" in home
    assert "التعلّم بالنطق المباشر" in home
    assert "التحدي الثنائي الصوتي" in home
    assert "جدول المراجعة الأسبوعي" in home
    assert "طلابنا <em>بيقولوا إيه</em>" in home
    assert "/admin/homepage/reviews/{{x.id}}/edit" in admin
    assert "homepage_review_updated" in home_router
