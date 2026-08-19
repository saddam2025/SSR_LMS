from pathlib import Path

def test_predeploy_owns_dependency_preparation():
    railway = Path("railway.toml").read_text(encoding="utf-8")
    start = Path("container-start.sh").read_text(encoding="utf-8")
    assert 'preDeployCommand = ["python -m app.deploy_prepare"]' in railway
    assert 'healthcheckPath = "/ready"' in railway
    assert 'python -m app.preflight' not in start

def test_production_import_has_no_schema_ddl():
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert 'if os.getenv("ENV", "development").lower() != "production":\n    ensure_schema()' in main

def test_security_does_not_connect_redis_at_import():
    security = Path("app/security.py").read_text(encoding="utf-8")
    assert '_rate_limit_redis' in security
    assert '_redis.ping()' not in security
