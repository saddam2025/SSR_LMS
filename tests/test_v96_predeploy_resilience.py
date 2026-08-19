
from pathlib import Path


def test_web_boot_uses_core_gate_not_full_integration_gate():
    main = Path("app/main.py").read_text(encoding="utf-8")
    assert "enforce_production_core()" in main
    assert "enforce_production_baseline()" not in main


def test_predeploy_does_not_block_on_redis_or_r2_by_default():
    src = Path("app/preflight.py").read_text(encoding="utf-8")
    assert "_redis_advisory_check" in src
    assert "PREDEPLOY WARNING: Redis unavailable" in src
    assert 'STORAGE_PREFLIGHT_ROUNDTRIP' in src


def test_schema_indexes_run_only_after_schema_validation():
    src = Path("app/preflight.py").read_text(encoding="utf-8")
    assert src.index("add_missing_columns_safely()") < src.index("validate_schema()") < src.index("ensure_performance_indexes()")


def test_additive_postgres_migration_is_serialized_and_conservative():
    src = Path("app/schema_migrate.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in src
    assert "Unsafe automatic migration" in src
    assert "DROP DEFAULT" in src
