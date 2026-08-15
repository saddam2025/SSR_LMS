
import os, re, hmac, hashlib
from fastapi.testclient import TestClient
import app.main as mainmod
from app.main import app
from app.seed import run
from app.db import SessionLocal
from app.models import User, OTPChallenge
from app.payment import configured, verify_transaction_hmac

run()

# Paymob must not be reported ready without HMAC.
saved={k:os.environ.get(k) for k in ["PAYMOB_SECRET_KEY","PAYMOB_PUBLIC_KEY","PAYMOB_INTEGRATION_ID","PAYMOB_HMAC_SECRET"]}
try:
    os.environ["PAYMOB_SECRET_KEY"]="s"
    os.environ["PAYMOB_PUBLIC_KEY"]="p"
    os.environ["PAYMOB_INTEGRATION_ID"]="123"
    os.environ.pop("PAYMOB_HMAC_SECRET",None)
    assert configured() is False
    os.environ["PAYMOB_HMAC_SECRET"]="h"
    assert configured() is True
finally:
    for k,v in saved.items():
        if v is None: os.environ.pop(k,None)
        else: os.environ[k]=v

# Verify HMAC helper with a synthetic callback.
secret="test-hmac-secret"
os.environ["PAYMOB_HMAC_SECRET"]=secret
obj={
 "amount_cents":10000,"created_at":"2026-08-12T10:00:00","currency":"EGP","error_occured":False,
 "has_parent_transaction":False,"id":987,"integration_id":123,"is_3d_secure":True,"is_auth":False,
 "is_capture":False,"is_refunded":False,"is_standalone_payment":True,"is_voided":False,
 "order":{"id":55},"owner":44,"pending":False,
 "source_data":{"pan":"1234","sub_type":"MasterCard","type":"card"},"success":True
}
vals=[obj["amount_cents"],obj["created_at"],obj["currency"],obj["error_occured"],obj["has_parent_transaction"],obj["id"],
      obj["integration_id"],obj["is_3d_secure"],obj["is_auth"],obj["is_capture"],obj["is_refunded"],obj["is_standalone_payment"],
      obj["is_voided"],obj["order"]["id"],obj["owner"],obj["pending"],obj["source_data"]["pan"],obj["source_data"]["sub_type"],
      obj["source_data"]["type"],obj["success"]]
def norm(v):
    if isinstance(v,bool): return "true" if v else "false"
    return str(v if v is not None else "")
sig=hmac.new(secret.encode(),"".join(norm(x) for x in vals).encode(),hashlib.sha512).hexdigest()
assert verify_transaction_hmac(obj,sig)
assert not verify_transaction_hmac(obj,"bad")

# OTP delivery failure must invalidate the generated challenge.
db=SessionLocal()
u=db.query(User).filter_by(email="student@ragab-seddik.local").first()
orig=mainmod._send_otp
def fail(*args,**kwargs):
    raise mainmod.HTTPException(503,"sms down")
mainmod._send_otp=fail
try:
    try:
        mainmod.create_otp(db,u,"01060309494","login")
        raise AssertionError("expected failure")
    except mainmod.HTTPException as e:
        assert e.status_code==503
    ch=db.query(OTPChallenge).filter_by(user_id=u.id,purpose="login").order_by(OTPChallenge.id.desc()).first()
    assert ch is not None and ch.used_at is not None
finally:
    mainmod._send_otp=orig
    db.close()

print("LIVE INTEGRATIONS REGRESSION OK")
