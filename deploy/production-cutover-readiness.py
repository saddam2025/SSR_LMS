#!/usr/bin/env python3
"""V85 production cutover readiness gate.

Fail-closed decision gate. It never changes DNS, deploys resources, or prints secrets.
It requires successful V84 staging acceptance plus production secret readiness and
explicit operational evidence for rollback, first-user acceptance, and monitoring.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        return data
    except Exception:
        return {"go": False, "error": "invalid JSON evidence"}


def evidence_check(name: str, path: Path | None, assertions: tuple[str, ...]) -> dict:
    if path is None or not path.exists():
        return {"name": name, "status": "FAIL", "detail": "evidence missing"}
    data = load_json(path)
    if data.get("go") is not True:
        return {"name": name, "status": "FAIL", "detail": data.get("summary") or data.get("error") or "evidence reports NO-GO"}
    missing = [k for k in assertions if data.get(k) is not True]
    if missing:
        return {"name": name, "status": "FAIL", "detail": "missing PASS assertions: " + ", ".join(missing)}
    return {"name": name, "status": "PASS", "detail": "evidence validated", "timestamp": data.get("timestamp")}


def run_secret_gate(prod_env: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, str(DEPLOY / "secret-readiness.py"), "--production", str(prod_env)],
        cwd=ROOT, text=True, capture_output=True, timeout=120,
    )
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 4000:
        out = out[-4000:]
    return {"name": "production_secret_readiness", "status": "PASS" if proc.returncode == 0 else "FAIL", "detail": out or "secret gate completed"}


def staging_gate(path: Path) -> dict:
    if not path.exists():
        return {"name": "v84_staging_acceptance", "status": "FAIL", "detail": "V84 report not found"}
    data = load_json(path)
    ok = data.get("version") == "V84" and data.get("environment") == "staging" and data.get("go") is True
    return {"name": "v84_staging_acceptance", "status": "PASS" if ok else "FAIL", "detail": "V84 staging GO verified" if ok else "V84 staging is not GO"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--v84-report", type=Path, required=True)
    ap.add_argument("--production-env", type=Path, required=True)
    ap.add_argument("--rollback-evidence", type=Path, required=True)
    ap.add_argument("--first-user-evidence", type=Path, required=True)
    ap.add_argument("--monitoring-evidence", type=Path, required=True)
    ap.add_argument("--json-report", type=Path, default=ROOT / "artifacts" / "v85-production-cutover-readiness.json")
    args = ap.parse_args()

    checks = [staging_gate(args.v84_report)]
    if args.production_env.exists():
        checks.append(run_secret_gate(args.production_env))
    else:
        checks.append({"name": "production_secret_readiness", "status": "FAIL", "detail": "production env file missing"})

    checks.append(evidence_check("rollback_plan", args.rollback_evidence, (
        "rollback_owner_assigned", "previous_release_available", "database_restore_path_verified", "dns_rollback_steps_verified")))
    checks.append(evidence_check("first_user_acceptance", args.first_user_evidence, (
        "student_login_ok", "course_access_ok", "protected_video_ok", "logout_ok")))
    checks.append(evidence_check("post_cutover_monitoring", args.monitoring_evidence, (
        "health_monitoring_ready", "error_monitoring_ready", "db_redis_monitoring_ready", "stream_webhook_monitoring_ready")))

    failed = [c for c in checks if c["status"] == "FAIL"]
    report = {
        "version": "V85",
        "timestamp": int(time.time()),
        "environment": "production-cutover-readiness",
        "checks": checks,
        "go": not failed,
        "decision": "GO_TO_CUTOVER_WINDOW" if not failed else "NO_GO_REMAIN_ON_STAGING",
        "safety": {
            "dns_changed": False,
            "deployment_performed": False,
            "secrets_printed": False,
        },
        "required_after_cutover": [
            "run production-acceptance.sh",
            "run post-cutover-monitor.sh during the observation window",
            "execute first real user acceptance and record evidence",
            "rollback immediately on sustained readiness/5xx/auth/payment/media failure",
        ],
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("V85 PRODUCTION CUTOVER READINESS")
    for c in checks:
        print(f"[{c['status']}] {c['name']}: {c['detail']}")
    print(report["decision"])
    print(f"Report: {args.json_report}")
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
