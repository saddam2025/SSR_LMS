import os, secrets, time, hmac, hashlib, base64, struct
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from datetime import datetime, timedelta
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

if os.getenv("ENV", "development").lower() == "test":
    password_hash = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
else:
    password_hash = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
APP_SECRET = os.getenv("APP_SECRET", "dev-secret-change-this-immediately")
MAX_DEVICES = int(os.getenv("MAX_DEVICES_PER_USER", "2"))
SESSION_IDLE_MINUTES = int(os.getenv("SESSION_IDLE_MINUTES", "45"))
SESSION_ABSOLUTE_HOURS = int(os.getenv("SESSION_ABSOLUTE_HOURS", "24"))
STUDENT_SINGLE_SESSION = os.getenv("STUDENT_SINGLE_SESSION", "true").lower() in {"1", "true", "yes", "on"}
REQUIRE_STAFF_MFA = os.getenv("REQUIRE_STAFF_MFA", "false").lower() in {"1", "true", "yes", "on"}

if os.getenv("ENV") == "production":
    if len(APP_SECRET) < 64 or APP_SECRET.startswith("dev-secret") or APP_SECRET.startswith("REPLACE_"):
        raise RuntimeError("APP_SECRET must be a unique random secret of at least 64 characters in production")

_IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"
_REDIS_CONFIGURED = bool(os.getenv("REDIS_URL", "").strip())

def _rate_limit_redis():
    # Reuse the retrying shared Redis client instead of connecting at import time.
    try:
        from .cache import client as cache_client
        return cache_client()
    except Exception:
        return None

_fallback_attempts: dict[str, tuple[int, float]] = {}

def hash_password(password: str) -> str:
    return password_hash.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return password_hash.verify(hashed, password)
    except Exception:
        return False

def password_needs_rehash(hashed: str) -> bool:
    try:
        return password_hash.check_needs_rehash(hashed)
    except Exception:
        return True

def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()

def ensure_csrf(session: dict) -> str:
    token = session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf"] = token
    return token

def check_csrf(session: dict, token: str | None) -> bool:
    expected = session.get("csrf", "")
    return bool(token and expected and hmac.compare_digest(token, expected))

def _rl_key(key: str) -> str:
    return "lms:login:" + sha256(key)[:32]

def login_allowed(key: str, limit: int = 6, window: int = 600) -> bool:
    c = _rate_limit_redis()
    if c:
        value = c.get(_rl_key(key))
        return int(value or 0) < limit
    # In multi-worker production, never silently downgrade a shared login limiter
    # to process-local state when Redis is configured but temporarily unavailable.
    if _IS_PRODUCTION and _REDIS_CONFIGURED:
        return False
    now = time.time()
    count, reset = _fallback_attempts.get(key, (0, now + window))
    if now > reset:
        _fallback_attempts[key] = (0, now + window)
        return True
    return count < limit

def record_failed_login(key: str, window: int = 600):
    c = _rate_limit_redis()
    if c:
        k = _rl_key(key)
        pipe = c.pipeline()
        pipe.incr(k)
        pipe.expire(k, window, nx=True)
        pipe.execute()
        return
    if _IS_PRODUCTION and _REDIS_CONFIGURED:
        return
    now = time.time()
    count, reset = _fallback_attempts.get(key, (0, now + window))
    if now > reset:
        count, reset = 0, now + window
    _fallback_attempts[key] = (count + 1, reset)

def clear_failed_logins(key: str):
    c = _rate_limit_redis()
    if c:
        c.delete(_rl_key(key))
    _fallback_attempts.pop(key, None)

def create_session_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(48)
    return raw, sha256(raw)

def session_absolute_expiry() -> datetime:
    return datetime.utcnow() + timedelta(hours=SESSION_ABSOLUTE_HOURS)

def session_idle_deadline(last_seen: datetime) -> datetime:
    return last_seen + timedelta(minutes=SESSION_IDLE_MINUTES)

def device_fingerprint(user_agent: str, accept_language: str, device_token: str = "") -> str:
    # The persistent random device token prevents two computers with the same
    # browser/OS/language from collapsing into one logical device. It is never
    # stored in plaintext server-side; only this keyed fingerprint is stored.
    material = f"{user_agent[:240]}|{accept_language[:80]}|{device_token[:160]}"
    return hmac.new(APP_SECRET.encode(), material.encode(), hashlib.sha256).hexdigest()

def sign_lesson(lesson_id: int, user_id: int, session_hash: str, ttl: int = 300) -> str:
    exp = int(time.time()) + ttl
    payload = f"{lesson_id}:{user_id}:{session_hash[:24]}:{exp}"
    sig = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"

def verify_lesson_signature(token: str, lesson_id: int, user_id: int, session_hash: str) -> bool:
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
        if exp < int(time.time()):
            return False
        payload = f"{lesson_id}:{user_id}:{session_hash[:24]}:{exp}"
        expected = hmac.new(APP_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(sig, expected)
    except Exception:
        return False

def encrypt_secret(value: str) -> str:
    key = hashlib.sha256(("mfa:" + APP_SECRET).encode()).digest()
    nonce = secrets.token_bytes(12)
    ct = AESGCM(key).encrypt(nonce, value.encode(), b"lms-mfa-v1")
    return base64.urlsafe_b64encode(nonce + ct).decode()

def decrypt_secret(value: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(value.encode())
        key = hashlib.sha256(("mfa:" + APP_SECRET).encode()).digest()
        return AESGCM(key).decrypt(raw[:12], raw[12:], b"lms-mfa-v1").decode()
    except Exception:
        return ""

# RFC 6238 compatible TOTP (SHA-1, 6 digits, 30-second step)
def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")

def _b32decode(secret: str) -> bytes:
    clean = "".join(secret.strip().upper().split())
    clean += "=" * ((8 - len(clean) % 8) % 8)
    return base64.b32decode(clean, casefold=True)

def totp_code(secret: str, for_time: int | None = None) -> str:
    counter = int((for_time if for_time is not None else time.time()) // 30)
    digest = hmac.new(_b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"

def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    code = "".join(ch for ch in str(code) if ch.isdigit())
    if len(code) != 6:
        return False
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + step * 30), code) for step in range(-window, window + 1))

def totp_uri(secret: str, account: str, issuer: str = "Al-Mostashar LMS") -> str:
    from urllib.parse import quote
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
