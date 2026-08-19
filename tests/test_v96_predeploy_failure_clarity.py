from pathlib import Path


def test_preflight_validates_baseline_before_importing_db_layer():
    src = Path('app/preflight.py').read_text(encoding='utf-8')
    # DB/cache/schema imports must be lazy inside dependency preflight.
    prefix = src.split('def _database_preflight', 1)[0]
    assert 'from .db import engine' not in prefix
    assert 'from .cache import client as cache_client' not in prefix
    assert 'enforce_production_core()' in src


def test_deploy_prepare_bootstrap_import_is_after_preflight():
    src = Path('app/deploy_prepare.py').read_text(encoding='utf-8')
    assert src.index('run_preflight()') < src.index('from .bootstrap_admin import run as run_bootstrap_admin')
