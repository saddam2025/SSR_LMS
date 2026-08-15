from pathlib import Path
import subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_v88_handoff_docs_exist():
    assert (ROOT/"deploy"/"DEPLOYMENT-HANDOFF-V88.md").is_file()
    assert (ROOT/"deploy"/"PRODUCTION-ENV-REQUIREMENTS-V88.md").is_file()
def test_v88_checker_is_non_mutating():
    s=(ROOT/"deploy"/"release-candidate-check.py").read_text()
    assert "wrangler deploy" not in s
    assert "dns_changed" not in s
    assert "No deployment or DNS mutation performed." in s
