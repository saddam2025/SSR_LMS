from pathlib import Path
import ast
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_v83_files_exist_and_parse():
    required = [
        ROOT / 'deploy' / 'STAGING-ENV-TEMPLATE.env',
        ROOT / 'deploy' / 'dns-tls-readiness.py',
        ROOT / 'deploy' / 'staging-bringup.py',
        ROOT / 'deploy' / 'v83-staging-go-no-go.sh',
        ROOT / 'STAGING-BRINGUP-V83.md',
    ]
    for p in required:
        assert p.exists(), p
    ast.parse((ROOT / 'deploy' / 'dns-tls-readiness.py').read_text(encoding='utf-8'))
    ast.parse((ROOT / 'deploy' / 'staging-bringup.py').read_text(encoding='utf-8'))


def test_template_is_staging_and_has_no_real_secret_material():
    txt = (ROOT / 'deploy' / 'STAGING-ENV-TEMPLATE.env').read_text(encoding='utf-8')
    assert 'staging-api.ragab-seddik.com' in txt
    assert 'staging-student.ragab-seddik.com' in txt
    assert 'RUN_SEED_ON_START=false' in txt
    assert 'ALLOW_DIRECT_VIDEO_PROXY=false' in txt
    assert 'REPLACE_WITH_STAGING_' in txt


def test_bringup_fails_closed_on_placeholder_env(tmp_path):
    src = (ROOT / 'deploy' / 'STAGING-ENV-TEMPLATE.env').read_text(encoding='utf-8')
    env = tmp_path / 'staging.env'
    env.write_text(src, encoding='utf-8')
    report = tmp_path / 'report.json'
    proc = subprocess.run([
        sys.executable, str(ROOT / 'deploy' / 'staging-bringup.py'),
        '--env-file', str(env), '--phase', 'predeploy', '--json-report', str(report)
    ], cwd=ROOT, text=True, capture_output=True, timeout=60)
    assert proc.returncode != 0
    assert 'NO-GO' in proc.stdout
    assert report.exists()
