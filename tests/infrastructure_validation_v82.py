from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parents[1]
validator=ROOT/'deploy/infrastructure-validation.py'
assert validator.exists()
s=validator.read_text(encoding='utf-8')
for token in ('select 1','PING ok','head_bucket','put_object','delete_object','api.cloudflare.com/client/v4/accounts/','PAYMOB_INTEGRATION_ID'):
    assert token in s, token
assert '--write-canary' in s
ast.parse(s)
gate=(ROOT/'deploy/v82-go-no-go.sh').read_text(encoding='utf-8')
assert 'R2_WRITE_CANARY' in gate and 'secret-readiness.py' in gate
assert (ROOT/'REAL-INFRASTRUCTURE-VALIDATION-V82.md').exists()
print('V82 INFRASTRUCTURE VALIDATION CONTRACT: PASS')
