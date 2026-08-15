"""Architecture-aware release gate."""
import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
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

def config(rel):
    return json.loads((REPO/rel).read_text(encoding='utf-8'))

def run_static_checks():
    require(read("VERSION").strip() == EXPECTED, "platform VERSION mismatch")
    require((REPO / "VERSION").read_text(encoding="utf-8").strip() == EXPECTED, "root VERSION mismatch")
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
    require("python -m app.preflight" in read("container-start.sh"), "container preflight missing")
    require("HEALTHCHECK" in read("Dockerfile") and "/ready" in read("Dockerfile"), "container healthcheck missing")
    require((ROOT / "ops/backup-postgres.sh").exists() and (ROOT / "ops/restore-postgres.sh").exists(), "backup/restore scripts missing")
    require((ROOT/'deploy/staging-acceptance.sh').exists(), 'staging acceptance script missing')

    require((ROOT/'deploy/secret-readiness.py').exists(), 'secret readiness gate missing')
    require((ROOT/'deploy/production-acceptance.sh').exists(), 'production acceptance script missing')
    require((ROOT/'deploy/LAUNCH-READINESS-V81.md').exists(), 'V81 launch readiness guide missing')
    require((ROOT/'deploy/infrastructure-validation.py').exists(), 'V82 infrastructure validator missing')
    require((ROOT/'deploy/v82-go-no-go.sh').exists(), 'V82 go/no-go gate missing')
    require((ROOT/'REAL-INFRASTRUCTURE-VALIDATION-V82.md').exists(), 'V82 validation guide missing')
    require((ROOT/'deploy/backup-restore-drill.sh').exists(), 'restore drill script missing')

    require((ROOT/'deploy/STAGING-ENV-TEMPLATE.env').exists(), 'V83 staging env template missing')
    require((ROOT/'deploy/dns-tls-readiness.py').exists(), 'V83 DNS/TLS readiness checker missing')
    require((ROOT/'deploy/staging-bringup.py').exists(), 'V83 staging bring-up orchestrator missing')
    require((ROOT/'deploy/v83-staging-go-no-go.sh').exists(), 'V83 staging go/no-go wrapper missing')
    require((ROOT/'STAGING-BRINGUP-V83.md').exists(), 'V83 staging bring-up guide missing')
    require((ROOT/'deploy/operational-acceptance.py').exists(), 'V84 operational acceptance aggregator missing')
    require((ROOT/'deploy/v84-staging-acceptance.sh').exists(), 'V84 staging acceptance wrapper missing')
    require((ROOT/'STAGING-OPERATIONAL-ACCEPTANCE-V84.md').exists(), 'V84 operational acceptance guide missing')
    for evidence in ('stream-tus.json','backup-restore.json','paymob-test.json'):
        require((ROOT/'deploy/evidence-templates'/evidence).exists(), 'V84 evidence template missing: ' + evidence)
    require((ROOT/'deploy/production-cutover-checklist.md').exists(), 'production cutover checklist missing')
    require((ROOT/'deploy/production-cutover-readiness.py').exists(), 'V85 production cutover readiness gate missing')
    require((ROOT/'deploy/v85-go-no-go.sh').exists(), 'V85 go/no-go wrapper missing')
    require((ROOT/'deploy/post-cutover-monitor.sh').exists(), 'V85 post-cutover monitor missing')
    require((ROOT/'PRODUCTION-CUTOVER-READINESS-V85.md').exists(), 'V85 cutover runbook missing')
    require((ROOT/'deploy/build-pages.py').exists(), 'Pages build tool missing')
    require((ROOT/'frontend/_headers').exists() and (ROOT/'frontend/_redirects').exists(), 'Pages headers/redirects missing')
    require('https://api.ragab-seddik.com' in read('frontend/config.js'), 'production student frontend API_BASE mismatch')
    headers=read('frontend/_headers')
    require('Content-Security-Policy:' in headers and 'https://api.ragab-seddik.com' in headers, 'Pages CSP incomplete')
    prod=config('cloudflare/wrangler.jsonc'); stage=config('cloudflare/wrangler.staging.jsonc')
    prod_domains={x.get('pattern') for x in prod.get('routes',[])}
    require('api.ragab-seddik.com' in prod_domains, 'production API custom domain missing')
    require(prod.get('vars',{}).get('FRONTEND_ORIGINS') == 'https://student.ragab-seddik.com', 'production frontend CORS origin mismatch')
    require(stage.get('routes') == [{'pattern':'staging-api.ragab-seddik.com','custom_domain':True}], 'staging API domain mismatch')
    require(stage.get('vars',{}).get('FRONTEND_ORIGINS') == 'https://staging-student.ragab-seddik.com', 'staging frontend origin mismatch')
    require(prod.get('vars',{}).get('RUN_SEED_ON_START') == 'false' and stage.get('vars',{}).get('RUN_SEED_ON_START') == 'false', 'automatic seed must be disabled in production/staging')
    worker=(REPO/'cloudflare/src/index.js').read_text(encoding='utf-8')
    require('function allowedHost(hostname, env)' in worker, 'Worker host validation must be runtime-configured')
    require('String(runtimeEnv.PUBLIC_BASE_URL' in worker, 'Worker PUBLIC_BASE_URL must come from runtime vars')
    env = read(".env.example")
    for required in ("DB_POOL_SIZE=", "WEB_CONCURRENCY=", "LOG_LEVEL=", "REDIS_RETRY_SECONDS=", "FRONTEND_ORIGINS=https://student.ragab-seddik.com"):
        require(required in env, "missing production env setting: " + required)
    require("ALLOW_DIRECT_VIDEO_PROXY=false" in env, "direct video must default disabled")
    require("REQUIRE_STAFF_MFA=true" in env, "staff MFA must default required")
    suspicious = re.compile(r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD)[A-Z0-9_]*[ \t]*=[ \t]*(?!REPLACE_|$)([^\s#]{20,})$")
    for rel in (".env.example", "CLOUDFLARE-PRODUCTION-ENV-TEMPLATE.env"):
        require(not suspicious.search(read(rel)), "possible literal secret in " + rel)
    print(f"{EXPECTED} STATIC RELEASE CHECK OK")

if __name__ == "__main__":
    run_static_checks()
