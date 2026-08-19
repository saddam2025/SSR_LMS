from pathlib import Path
import html
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "app" / "templates"


def _render_home():
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html", "xml"]))
    return html.unescape(env.get_template("home.html").render(
        request=None, user=None, csrf="", unread_notifications=0,
        staff_mfa_pending=False, role_labels={}, is_production=False,
        courses=[], reels=[], honors=[], reels_enabled=False, honors_enabled=False,
    ))


def test_marketing_sections_render_with_real_platform_features():
    page = _render_home()
    required = (
        'id="platform-benefits"',
        'مميزات <em>تفرق معاك</em> فعلاً',
        'مدعومة بالمساعد الذكي',
        'تصحيح فوري للاختبارات',
        'منهج منظم لكل صف',
        'تركيز حقيقي على الامتحان',
        'مذكرات وملخصات',
        'متابعة وتقرير تقدم',
        'دعم وقت ما تحتاج',
        'تتعلم بأمان من أجهزتك',
        'محتوى وتجربة سريعة',
        'id="platform-difference"',
        'id="why"',
        'ليه <em>منصة المستشار</em>؟',
        'تصحيح آلي فوري بدرجات موزونة',
        'مساعد ذكي مرتبط بمحتوى الدرس',
        'تقارير ومتابعة لولي الأمر',
        'حماية للمحتوى والجلسات والأجهزة',
        'مجتمع ودعم رسمي لكل صف',
        'ابدأ الآن وجرب بنفسك',
    )
    for marker in required:
        assert marker in page


def test_marketing_sections_are_responsive_and_native_not_images():
    css = (ROOT / "app/static/home-v96.css").read_text(encoding="utf-8")
    home = (ROOT / "app/templates/home.html").read_text(encoding="utf-8")
    assert '.mostashar-benefit-grid{display:grid;grid-template-columns:repeat(3' in css
    assert '@media(max-width:1024px)' in css
    assert '@media(max-width:680px)' in css
    assert '.mostashar-compare-wrap' in css
    assert 'Screenshot 2026-08-17' not in home
    assert '<img' not in home[home.index('<section class="mostashar-benefits"'):home.index('<section class="wael-journey">')]


def test_homepage_marketing_flow_is_ordered_and_not_duplicated():
    page = _render_home()
    anchors = [
        'id="grades"',
        'id="courses"',
        'id="platform-benefits"',
        'id="smart-assistant"',
        'class="wael-journey"',
        'id="why"',
        'id="community"',
        'class="whatsapp-support-section"',
        'class="wael-cta"',
    ]
    positions = [page.index(marker) for marker in anchors]
    assert positions == sorted(positions)
    assert 'class="wael-why"' not in page
    assert page.count('ليه <em>منصة المستشار</em>؟') == 1
