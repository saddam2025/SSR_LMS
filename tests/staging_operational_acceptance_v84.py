from __future__ import annotations
import importlib.util, json, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
assert (ROOT/'VERSION').read_text().strip()=='V84'
p=ROOT/'deploy'/'operational-acceptance.py'
spec=importlib.util.spec_from_file_location('v84_acceptance',p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

td=Path(tempfile.mkdtemp())
fixtures={
 'stream_tus': {'go':True,'upload_resumable':True,'playback_ok':True,'authorization_ok':True},
 'backup_restore': {'go':True,'backup_created':True,'restore_completed':True,'integrity_verified':True},
 'paymob_test': {'go':True,'payment_success':True,'webhook_verified':True,'subscription_activated':True},
}
for kind,data in fixtures.items():
    f=td/f'{kind}.json'; f.write_text(json.dumps(data),encoding='utf-8')
    assert m.validate_evidence(kind,f)['status']=='PASS'

bad=td/'bad.json'; bad.write_text(json.dumps({'go':True,'payment_success':True}),encoding='utf-8')
assert m.validate_evidence('paymob_test',bad)['status']=='FAIL'
assert m.validate_evidence('stream_tus',None)['status']=='FAIL'

for name in ('stream-tus.json','backup-restore.json','paymob-test.json'):
    d=json.loads((ROOT/'deploy'/'evidence-templates'/name).read_text())
    assert d['go'] is False

print('V84 STAGING OPERATIONAL ACCEPTANCE CONTRACT: PASS')
