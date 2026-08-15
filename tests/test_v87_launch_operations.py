from pathlib import Path
import json, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
def test_v87_docs_and_monitor_are_safe(tmp_path):
    for n in ["INCIDENT-RUNBOOK-V87.md","LAUNCH-DAY-RUNBOOK-V87.md","ALERT-MATRIX-V87.md"]:
        assert (ROOT/"deploy"/n).is_file()
    script=(ROOT/"deploy"/"launch-24h-monitor.py").read_text()
    assert "read_only" in script and "dns_changed" in script
    assert "password" not in script.lower()
def test_v87_monitor_fail_closed(tmp_path):
    out=tmp_path/"r.json"
    p=subprocess.run([sys.executable,str(ROOT/"deploy"/"launch-24h-monitor.py"),
       "--api","http://127.0.0.1:9","--frontend","http://127.0.0.1:9",
       "--iterations","1","--output",str(out)],cwd=ROOT,capture_output=True,text=True,timeout=30)
    assert p.returncode != 0
    d=json.loads(out.read_text())
    assert d["go"] is False and d["failed_probes"] == 3
    assert d["safety"]["read_only"] is True
def test_main_still_bootstrap():
    s=(ROOT/"app"/"main.py").read_text()
    for verb in ("get","post","put","patch","delete"):
        assert f"@app.{verb}(" not in s
