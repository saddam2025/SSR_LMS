from app.main import app
from app import request_context
import app.main as mainmod

assert mainmod.current_user is request_context.current_user
assert mainmod.require_user is request_context.require_user
assert mainmod.require_role is request_context.require_role
assert mainmod.audit is request_context.audit
assert mainmod._session_record is request_context.session_record
assert app.state.require_user is request_context.require_user
assert app.state.require_role is request_context.require_role
assert app.state.audit is request_context.audit
print('V66 REQUEST CONTEXT EXTRACTION: PASS')
