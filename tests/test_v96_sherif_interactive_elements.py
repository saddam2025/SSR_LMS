import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sherif_reference_elements_are_native_and_wired():
    home = (ROOT / 'app/templates/home.html').read_text(encoding='utf-8')
    lab = (ROOT / 'app/templates/english_lab.html').read_text(encoding='utf-8')
    base = (ROOT / 'app/templates/base.html').read_text(encoding='utf-8')
    css = (ROOT / 'app/static/sherif-inspired-v96.css').read_text(encoding='utf-8')
    js = (ROOT / 'app/static/english-lab.js').read_text(encoding='utf-8')
    core = (ROOT / 'app/static/english-lab-core.js').read_text(encoding='utf-8')
    router = (ROOT / 'app/routers/english_tools.py').read_text(encoding='utf-8')

    for marker in ('id="english-hub"', 'id="interactive-lab"', 'id="about-ragab"', 'id="smart-assistant"'):
        assert marker in home
    for href in ('/english-lab#tense-lab','/english-lab#flashcards','/english-lab#quick-quiz','/english-lab#sentence-builder',
                 '/english-lab#speaking','/english-lab#listening','/english-lab#irregular','/english-lab#matching','/english-lab#reading','/english-lab#letters'):
        assert href in home
    assert 'href="#"' not in home
    assert 'مختبر الإنجليزي' in base and 'href="/english-lab"' in base
    assert "@router.get('/english-lab'" in router

    panel_ids = set(re.findall(r'id="([^"]+)" data-lab-panel', lab))
    target_ids = set(re.findall(r'data-target="([^"]+)"', lab))
    assert panel_ids == target_ids == {'tense-lab','flashcards','quick-quiz','sentence-builder','speaking','listening','irregular','matching','reading','letters'}
    assert 'english-lab-core.js' in lab and 'english-lab.js' in lab
    assert 'MostasharEnglishLabCore' in js and 'tenseForms' in core

    # Every static DOM id referenced by the JS helper exists in the template.
    referenced = set(re.findall(r"\$\('([^']+)'\)", js))
    template_ids = set(re.findall(r'id="([^"]+)"', lab))
    assert referenced <= template_ids, sorted(referenced - template_ids)
    assert '@media(max-width:900px)' in css and '@media(max-width:620px)' in css
