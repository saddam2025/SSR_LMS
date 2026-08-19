from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_teacher_bio_and_social_buttons_are_visible_and_wired():
    home = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/sherif-inspired-v96.css").read_text(encoding="utf-8")
    for text in (
        "تمهيدي الماجستير", "جامعة سوهاج", "Micro-teaching", "جامعة ستراثكلايد",
        "البكالوريا · الثانوية العامة · الأزهر الشريف", "حلول الواجبات", "امتحانات أونلاين",
        "فيديوهات قصيرة", "تواصل مباشر", "تابع المستشار على السوشيال ميديا",
    ):
        assert text in home
    for url in (
        "https://www.facebook.com/Elmustashar.RS/",
        "https://whatsapp.com/channel/0029VaeqHW88V0toN7GCLn2z",
        "https://www.tiktok.com/@ragab.seddik",
        "https://www.youtube.com/@Ragab.Seddik",
        "https://www.facebook.com/share/g/19bNfZ1YcQ/?mibextid=wwXIfr",
        "https://t.me/MrRagabSeddik",
    ):
        assert f'href="{url}"' in home
    assert 'teacher-social-strip' in home and '.teacher-social-strip' in css
    assert 'href="#"' not in home


def test_about_teacher_has_no_redundant_portrait():
    home = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
    assert '<div class="sherif-teacher-photo">' not in home

