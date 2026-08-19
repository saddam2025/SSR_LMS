import os
from urllib.parse import urlparse

PLACEHOLDERS = ("REPLACE_", "CHANGE_ME", "changeme", "example.com")

def _set(name: str) -> bool:
    v = os.getenv(name, "").strip()
    return bool(v) and not any(p.lower() in v.lower() for p in PLACEHOLDERS)

def _core_checks() -> dict:
    env = os.getenv("ENV", "development").lower()
    public = os.getenv("PUBLIC_BASE_URL", "").strip()
    db = os.getenv("DATABASE_URL", "").strip()
    return {
        "production_mode": env == "production",
        "https_public_url": public.startswith("https://") and bool(urlparse(public).hostname),
        "strong_app_secret": _set("APP_SECRET") and len(os.getenv("APP_SECRET", "")) >= 64,
        "postgres_database": db.startswith("postgresql+") or db.startswith("postgresql://") or db.startswith("postgres://"),
        "admin_credentials": _set("ADMIN_EMAIL") and _set("ADMIN_PASSWORD") and len(os.getenv("ADMIN_PASSWORD", "")) >= 14,
        "allowed_hosts": _set("ALLOWED_HOSTS") or (public.startswith("https://") and bool(urlparse(public).hostname)),
        "staff_mfa_required": os.getenv("REQUIRE_STAFF_MFA", "false").lower() in {"1", "true", "yes", "on"},
    }

def production_status() -> dict:
    public = os.getenv("PUBLIC_BASE_URL", "").strip()
    checks = dict(_core_checks())
    checks.update({
        # Required for full-scale launch, but not for bootstrapping the web service.
        # Railway pre-deploy only blocks on core configuration + PostgreSQL schema.
        "redis_configured": _set("REDIS_URL"),
        "durable_media_storage": (
            os.getenv("STORAGE_BACKEND", "").lower() == "s3"
            and all(_set(x) for x in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"))
        ),
    })
    cloudflare_deployment = os.getenv("CLOUDFLARE_DEPLOYMENT", "false").lower() in {"1", "true", "yes", "on"}
    if cloudflare_deployment:
        r2_endpoint = os.getenv("S3_ENDPOINT_URL", "").strip().lower()
        video_hosts = os.getenv("VIDEO_ALLOWED_HOSTS", "").lower()
        allowed_hosts = {x.strip().lower() for x in os.getenv("ALLOWED_HOSTS", "").split(",") if x.strip()}
        separated_frontend = os.getenv("SEPARATED_FRONTEND_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
        frontend_origin = os.getenv("FRONTEND_PRIMARY_ORIGIN", "").strip().rstrip("/")
        frontend_origins = {x.strip().rstrip("/") for x in os.getenv("FRONTEND_ORIGINS", "").split(",") if x.strip()}
        frontend_parsed = urlparse(frontend_origin) if frontend_origin else None
        public_host = (urlparse(public).hostname or "").lower()
        checks.update({
            "cloudflare_edge_secret": len(os.getenv("CF_EDGE_SIGNING_SECRET", "")) >= 32,
            "cloudflare_r2_storage": (
                os.getenv("STORAGE_BACKEND", "").lower() == "s3"
                and r2_endpoint.startswith("https://")
                and r2_endpoint.endswith(".r2.cloudflarestorage.com")
                and all(_set(x) for x in ("S3_BUCKET", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY"))
            ),
            "cloudflare_stream_hosts": "cloudflarestream.com" in video_hosts and "videodelivery.net" in video_hosts,
            "cloudflare_stream_upload": len(os.getenv("CF_ACCOUNT_ID", "").strip()) == 32 and len(os.getenv("CF_STREAM_API_TOKEN", "").strip()) >= 20,
            "cloudflare_stream_customer_code": _set("CF_STREAM_CUSTOMER_CODE"),
            "cloudflare_direct_video_disabled": os.getenv("ALLOW_DIRECT_VIDEO_PROXY", "false").lower() not in {"1", "true", "yes", "on"},
            "cloudflare_api_host": bool(public_host and public_host in allowed_hosts),
            "separated_frontend_cors": (not separated_frontend) or bool(frontend_parsed and frontend_parsed.scheme == "https" and frontend_parsed.hostname and frontend_origin in frontend_origins),
        })
    optional = {
        "paymob": all(_set(x) for x in ("PAYMOB_SECRET_KEY","PAYMOB_PUBLIC_KEY","PAYMOB_HMAC_SECRET","PAYMOB_INTEGRATION_ID")),
        "sms_otp": _set("OTP_SMS_WEBHOOK_URL"),
        "s3_storage": os.getenv("STORAGE_BACKEND", "local").lower() == "s3" and all(_set(x) for x in ("S3_BUCKET","S3_ACCESS_KEY_ID","S3_SECRET_ACCESS_KEY")),
        "drm": bool(os.getenv("DRM_PROVIDER", "").strip()) and _set("DRM_LICENSE_SERVER_URL"),
        "video_allowlist": _set("VIDEO_ALLOWED_HOSTS"),
    }
    core = _core_checks()
    core_ok = all(core.values())
    required_ok = all(checks.values())
    return {"core": core, "required": checks, "integrations": optional, "core_ok": core_ok, "required_ok": required_ok, "full_launch_ok": required_ok and all(optional.values())}

def enforce_production_core():
    if os.getenv("ENV", "development").lower() != "production":
        return
    s = production_status()
    missing = [k for k,v in s["core"].items() if not v]
    if missing:
        raise RuntimeError("Unsafe production core configuration; missing/invalid: " + ", ".join(missing))

def enforce_production_baseline():
    """Strict full-launch gate used by audits, not by Railway bootstrapping."""
    if os.getenv("ENV", "development").lower() != "production":
        return
    s = production_status()
    missing = [k for k,v in s["required"].items() if not v]
    if missing:
        raise RuntimeError("Unsafe production configuration; missing/invalid: " + ", ".join(missing))
