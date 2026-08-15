from pathlib import Path
import ast

root = Path(__file__).resolve().parents[1]
router = root / 'app/routers/learning_runtime.py'
text = router.read_text(encoding='utf-8')
assert 'from .. import main' not in text
assert '_legacy' not in text
assert 'services.lesson_rendering' in text
assert 'services.study_intelligence' in text
assert 'services.template_rendering' in text

for rel in [
    'app/services/template_rendering.py',
    'app/services/lesson_rendering.py',
    'app/services/study_intelligence.py',
]:
    src = (root / rel).read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module not in {'main', 'app.main'}, f'{rel} imports main'
        if isinstance(node, ast.Import):
            assert all(alias.name not in {'main', 'app.main'} for alias in node.names), f'{rel} imports main'

from app.services.study_intelligence import study_tokens
assert 'lesson' in study_tokens('How is this lesson explained?')
assert 'the' not in study_tokens('the lesson')
print('V72 LEARNING RUNTIME FULL DECOUPLING: PASS')
