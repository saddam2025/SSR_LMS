import os, hmac, hashlib, uuid
from urllib.parse import urlparse
import httpx

BASE = os.getenv("PAYMOB_BASE_URL", "https://accept.paymob.com").rstrip("/")
_parsed_base = urlparse(BASE)
if not _parsed_base.hostname or _parsed_base.username or _parsed_base.password or _parsed_base.scheme not in {"https", "http"}:
    raise RuntimeError("PAYMOB_BASE_URL is invalid")
if os.getenv("ENV") == "production" and _parsed_base.scheme != "https":
    raise RuntimeError("PAYMOB_BASE_URL must use HTTPS in production")

def configured():
    return all(os.getenv(k) for k in ("PAYMOB_SECRET_KEY","PAYMOB_PUBLIC_KEY","PAYMOB_INTEGRATION_ID","PAYMOB_HMAC_SECRET"))

def merchant_reference():
    return "RS-" + uuid.uuid4().hex[:20].upper()

def create_intention(*, amount_egp: float, course_title: str, reference: str, name: str, email: str, phone: str, base_url: str):
    if not configured():
        raise RuntimeError("Paymob credentials are not configured")
    cents = max(0, int(round(amount_egp * 100)))
    parts = (name.strip().split(maxsplit=1) + ["Student"])[:2]
    payload = {
        "amount": cents, "currency": "EGP",
        "payment_methods": [int(os.environ["PAYMOB_INTEGRATION_ID"])],
        "items": [{"name": course_title[:100], "amount": cents, "description": "Course subscription", "quantity": 1}],
        "billing_data": {"first_name": parts[0] or "Student", "last_name": parts[1] or "Student", "email": email,
                         "phone_number": phone or "+201000000000", "apartment":"NA","floor":"NA","street":"NA","building":"NA",
                         "shipping_method":"NA","postal_code":"NA","city":"Cairo","country":"EG","state":"Cairo"},
        "customer": {"first_name": parts[0] or "Student", "last_name": parts[1] or "Student", "email": email},
        "special_reference": reference,
        "notification_url": base_url.rstrip("/") + "/api/paymob/webhook",
        "redirection_url": base_url.rstrip("/") + "/payment/complete",
    }
    with httpx.Client(timeout=20) as client:
        r = client.post(BASE + "/v1/intention/", headers={"Authorization": "Token " + os.environ["PAYMOB_SECRET_KEY"]}, json=payload)
        r.raise_for_status(); data = r.json()
    secret = data["client_secret"]
    return data, f"{BASE}/unifiedcheckout/?publicKey={os.environ['PAYMOB_PUBLIC_KEY']}&clientSecret={secret}"

def verify_transaction_hmac(obj: dict, received: str) -> bool:
    secret = os.getenv("PAYMOB_HMAC_SECRET", "")
    if not secret or not received: return False
    sd=obj.get("source_data") or {}; order=obj.get("order") or {}
    vals=[obj.get("amount_cents"),obj.get("created_at"),obj.get("currency"),obj.get("error_occured"),obj.get("has_parent_transaction"),
          obj.get("id"),obj.get("integration_id"),obj.get("is_3d_secure"),obj.get("is_auth"),obj.get("is_capture"),obj.get("is_refunded"),
          obj.get("is_standalone_payment"),obj.get("is_voided"),order.get("id"),obj.get("owner"),obj.get("pending"),sd.get("pan"),sd.get("sub_type"),sd.get("type"),obj.get("success")]
    def norm(v):
        if isinstance(v,bool): return "true" if v else "false"
        return str(v if v is not None else "")
    computed=hmac.new(secret.encode(), "".join(norm(x) for x in vals).encode(), hashlib.sha512).hexdigest()
    return hmac.compare_digest(computed.lower(), received.lower())
