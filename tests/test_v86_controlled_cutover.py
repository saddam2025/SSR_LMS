from pathlib import Path
import json, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
DEPLOY=ROOT/"deploy"
def run(report, out):
    return subprocess.run([sys.executable,str(DEPLOY/"controlled-cutover.py"),
        "--v85-report",str(report),"--output",str(out)],cwd=ROOT,capture_output=True,text=True)
def test_v86_fail_closed_and_go_contract(tmp_path):
    no=tmp_path/"no.json"; no.write_text(json.dumps({"version":"V85","go":False,"decision":"NO_GO_REMAIN_ON_STAGING"}))
    out=tmp_path/"out.json"; p=run(no,out)
    assert p.returncode != 0
    d=json.loads(out.read_text()); assert d["decision"]=="NO_GO_DO_NOT_CUTOVER" and d["steps"]==[]
    go=tmp_path/"go.json"; go.write_text(json.dumps({"version":"V85","go":True,"decision":"GO_TO_CUTOVER_WINDOW"}))
    p=run(go,out); assert p.returncode==0
    d=json.loads(out.read_text()); assert d["decision"]=="CUTOVER_COMMAND_SHEET_READY"
    assert len(d["steps"]) >= 8
    assert d["safety"]=={"dns_changed":False,"deployment_performed":False,"secrets_printed":False}
def test_v86_main_remains_bootstrap():
    main=(ROOT/"app"/"main.py").read_text(encoding="utf-8")
    assert "@app.get(" not in main and "@app.post(" not in main and "@app.put(" not in main and "@app.delete(" not in main and "@app.patch(" not in main
