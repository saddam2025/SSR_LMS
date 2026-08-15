from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]

def test_no_database_artifacts_in_clean_tree():
    assert not [p for p in ROOT.rglob("*.db") if "__pycache__" not in p.parts]

def test_manifest_excludes_mutable_suffixes():
    s=(ROOT/"deploy"/"build-release-manifest.py").read_text()
    for ext in (".db",".sqlite",".sqlite3",".log",".pid"):
        assert ext in s

def test_production_database_url_is_fail_closed(tmp_path):
    env=os.environ.copy()
    env["ENV"]="production"
    env.pop("DATABASE_URL",None)
    code="import app.db"
    p=subprocess.run([sys.executable,"-c",code],cwd=ROOT,env=env,capture_output=True,text=True)
    assert p.returncode != 0
    assert "DATABASE_URL is required in production" in (p.stdout+p.stderr)
