from pathlib import Path


def test_security_dependency_floors_are_pinned_above_known_fixes():
    req = Path('requirements.txt').read_text(encoding='utf-8')
    required = {
        'starlette>=0.40,<1.0',
        'python-multipart>=0.0.31,<1',
        'cryptography>=46.0.5,<47',
        'pypdf>=6.16.1,<7',
        'pillow>=12.3,<13',
    }
    missing = sorted(required - set(line.strip() for line in req.splitlines()))
    assert not missing, f'missing security floors: {missing}'
