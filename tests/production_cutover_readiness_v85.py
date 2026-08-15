from pathlib import Path
import json, os, subprocess, sys, tempfile
ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'deploy'/'production-cutover-readiness.py'

def write(p,d): p.write_text(json.dumps(d), encoding='utf-8')

def main():
    assert (ROOT/'VERSION').read_text().strip()=='V85'
    text=(ROOT/'app'/'main.py').read_text(encoding='utf-8')
    assert '@app.get(' not in text and '@app.post(' not in text
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        # Current V84 NO-GO must block.
        prod=td/'prod.env'; prod.write_text('ENV=production\n', encoding='utf-8')
        ev=td/'ev'; ev.mkdir()
        write(ev/'rollback.json', {'go':True,'rollback_owner_assigned':True,'previous_release_available':True,'database_restore_path_verified':True,'dns_rollback_steps_verified':True})
        write(ev/'first.json', {'go':True,'student_login_ok':True,'course_access_ok':True,'protected_video_ok':True,'logout_ok':True})
        write(ev/'mon.json', {'go':True,'health_monitoring_ready':True,'error_monitoring_ready':True,'db_redis_monitoring_ready':True,'stream_webhook_monitoring_ready':True})
        out=td/'out.json'
        p=subprocess.run([sys.executable,str(SCRIPT),'--v84-report',str(ROOT/'artifacts'/'v84-operational-acceptance.json'),'--production-env',str(prod),'--rollback-evidence',str(ev/'rollback.json'),'--first-user-evidence',str(ev/'first.json'),'--monitoring-evidence',str(ev/'mon.json'),'--json-report',str(out)],cwd=ROOT,text=True,capture_output=True)
        assert p.returncode != 0
        data=json.loads(out.read_text())
        assert data['go'] is False and data['safety']['dns_changed'] is False
    print('V85 production cutover readiness contract: PASS')
if __name__=='__main__': main()
