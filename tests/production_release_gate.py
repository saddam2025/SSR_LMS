import os
from app.production import production_status
required = {
    "ENV":"production",
    "PUBLIC_BASE_URL":"https://example.test",
    "APP_SECRET":"x"*80,
    "DATABASE_URL":"postgresql://user:pass@db/test",
    "REDIS_URL":"redis://kv:6379/0",
    "ADMIN_EMAIL":"admin@example.test",
    "ADMIN_PASSWORD":"StrongAdminPass123!",
    "ALLOWED_HOSTS":"example.test",
    "REQUIRE_STAFF_MFA":"true",
    "PAYMOB_SECRET_KEY":"secret",
    "PAYMOB_PUBLIC_KEY":"public",
    "PAYMOB_HMAC_SECRET":"hmac",
    "PAYMOB_INTEGRATION_ID":"123",
    "OTP_SMS_WEBHOOK_URL":"https://sms.example.test/send",
    "STORAGE_BACKEND":"s3",
    "S3_BUCKET":"bucket",
    "S3_ACCESS_KEY_ID":"key",
    "S3_SECRET_ACCESS_KEY":"secret",
    "DRM_PROVIDER":"provider",
    "DRM_LICENSE_SERVER_URL":"https://drm.example.test/license",
    "VIDEO_ALLOWED_HOSTS":"video.example.test",
}
os.environ.update(required)
s=production_status()
assert s["required_ok"], s
assert s["full_launch_ok"], s
print("PRODUCTION RELEASE GATE OK")
