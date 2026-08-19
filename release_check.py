"""Architecture-aware release gate for the standalone Railway source package."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EXPECTED = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")

def require(ok: bool, message: str):
    if not ok:
        raise SystemExit("RELEASE CHECK FAILED: " + message)

def no_http_routes_in_main() -> bool:
    tree = ast.parse(read("app/main.py"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                    if isinstance(d.func.value, ast.Name) and d.func.value.id == "app" and d.func.attr in {"get","post","put","patch","delete"}:
                        return False
    return True

def run_static_checks():
    require(EXPECTED.startswith("V"), "invalid VERSION")
    require(no_http_routes_in_main(), "main.py must remain bootstrap-only")
    main = read("app/main.py")
    require("configure_logging()" in main, "logging bootstrap missing")
    require("metrics_middleware" in main and "security_headers" in main, "core middleware missing")
    obs = read("app/observability.py")
    require('getattr(route, "path", None)' in obs, "metrics must use route templates")
    require('response.headers["X-Request-ID"]' in obs, "request-id propagation missing")
    cache = read("app/cache.py")
    require("_local_allowed" in cache and "not (_IS_PRODUCTION and _REDIS_URL)" in cache, "production Redis fallback guard missing")
    require("_RETRY_SECONDS" in cache, "Redis reconnect policy missing")
    db = read("app/db.py")
    require("DATABASE_URL is required in production" in db, "production database fail-closed guard missing")
    require("DB_POOL_SIZE" in db and "DB_MAX_OVERFLOW" in db, "database pool tuning missing")
    require("python -m app.deploy_prepare" in read("railway.toml"), "Railway pre-deploy preparation missing")
    require('PORT:-8000' in read("container-start.sh"), "Railway PORT binding missing")
    require("HEALTHCHECK" in read("Dockerfile") and "/ready" in read("Dockerfile") and "os.getenv('PORT','8000')" in read("Dockerfile"), "container readiness healthcheck missing")
    require('healthcheckPath = "/ready"' in read("railway.toml"), "Railway readiness healthcheck mismatch")
    require('DIRECT_R2_UPLOAD_ENABLED=true' in read('.env.railway.example'), 'direct R2 upload must be enabled in production template')
    require('verify_storage_roundtrip' in read('app/preflight.py'), 'R2/S3 storage roundtrip preflight missing')
    require('WEB_CONCURRENCY=2' in read('.env.railway.example'), 'production worker default must be scale hardened')
    require((ROOT/'R2-CORS-POLICY-V96.json').exists(), 'R2 browser upload CORS policy missing')
    require('healthcheck.railway.app' in main, "Railway healthcheck host must be trusted in production")
    require((ROOT / "ops/backup-postgres.sh").exists() and (ROOT / "ops/restore-postgres.sh").exists(), "backup/restore scripts missing")
    for rel in (
        "deploy/staging-acceptance.sh", "deploy/secret-readiness.py", "deploy/production-acceptance.sh",
        "deploy/infrastructure-validation.py", "deploy/backup-restore-drill.sh", "deploy/operational-acceptance.py",
        "deploy/production-cutover-readiness.py", "deploy/controlled-cutover.py", "deploy/launch-24h-monitor.py",
    ):
        require((ROOT/rel).exists(), f"deployment tool missing: {rel}")
    require((ROOT/'frontend/_headers').exists() and (ROOT/'frontend/_redirects').exists(), 'frontend headers/redirects missing')
    require('window.location.origin' in read('frontend/config.js'), 'default frontend must use same-origin API_BASE')
    headers=read('frontend/_headers')
    require('Content-Security-Policy:' in headers, 'frontend CSP incomplete')
    env=read('.env.railway.example')
    for required in (
        'ENV=production', 'DATABASE_URL=${{Postgres.DATABASE_URL}}', 'REDIS_URL=${{Redis.REDIS_URL}}',
        'RUN_SEED_ON_START=false', 'REQUIRE_STAFF_MFA=true', 'ALLOW_DIRECT_VIDEO_PROXY=false',
        'STORAGE_BACKEND=s3', 'cloudflarestorage.com', 'CF_STREAM_API_TOKEN=', 'WEB_CONCURRENCY=',
    ):
        require(required in env, 'missing Railway production setting: '+required)
    suspicious = re.compile(r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*[ \t]*=[ \t]*(?!REPLACE_|$)([^\s#]{20,})$")
    for rel in ('.env.example','.env.railway.example','CLOUDFLARE-PRODUCTION-ENV-TEMPLATE.env'):
        require(not suspicious.search(read(rel)), 'possible literal secret in '+rel)
    av=json.loads(read('app/static/app-version.json'))
    require(av.get('version') == av.get('android_version') == av.get('windows_version'), 'client version metadata inconsistent')
    require(str(av.get('release','')).startswith(EXPECTED+'-'), 'client release metadata mismatch')
    print(f"{EXPECTED} STATIC RELEASE CHECK OK")

if __name__ == '__main__':
    run_static_checks()
