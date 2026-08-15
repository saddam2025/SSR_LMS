from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
ROOT = PLATFORM.parent
prod=(PLATFORM/'app/production.py').read_text()
tpl=(PLATFORM/'app/templates/account_security.html').read_text()
auth=(PLATFORM/'app/routers/auth.py').read_text()
assert 'staff_mfa_required' in prod
assert 'action="/account/security/mfa/enable"' in tpl
assert 'pending_secret' in tpl and 'otpauth_uri' in tpl
assert 'mfa_required=bool(REQUIRE_STAFF_MFA and u.role in STAFF_ROLES)' in auth
# Full multi-artifact releases may contain a sibling Cloudflare Worker. Railway-only source packages do not.
wrangler=ROOT/'cloudflare/wrangler.jsonc'
worker=ROOT/'cloudflare/src/index.js'
if wrangler.exists() and worker.exists():
    w=wrangler.read_text(); js=worker.read_text()
    assert '"workers_dev": false' in w
    assert '*.workers.dev' not in w
    assert 'host.endsWith(".workers.dev")' not in js
print('V42 security hardening regression: PASS')
