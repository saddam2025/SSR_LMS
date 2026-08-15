#!/usr/bin/env python3
"""V83 staging bring-up orchestrator.

Runs deployment gates in an explicit sequence and writes a single JSON result.
It never prints secret values. External-resource checks are executed only when requested.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"


def run_step(name: str, cmd: list[str], required: bool = True) -> dict:
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=180)
        ok = proc.returncode == 0
        # Keep logs useful but bounded; commands are designed not to print secrets.
        out = (proc.stdout + proc.stderr).strip()
        if len(out) > 5000:
            out = out[-5000:]
        return {
            "name": name,
            "status": "PASS" if ok else ("FAIL" if required else "WARN"),
            "required": required,
            "returncode": proc.returncode,
            "duration_seconds": round(time.time() - started, 3),
            "output": out,
        }
    except subprocess.TimeoutExpired:
        return {"name": name, "status": "FAIL" if required else "WARN", "required": required, "duration_seconds": round(time.time()-started,3), "output": "step timed out"}
    except Exception as exc:
        return {"name": name, "status": "FAIL" if required else "WARN", "required": required, "duration_seconds": round(time.time()-started,3), "output": f"{type(exc).__name__}: step failed"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--phase", choices=["predeploy", "postdeploy", "full"], default="predeploy")
    p.add_argument("--write-canary", action="store_true")
    p.add_argument("--api", default="https://staging-api.ragab-seddik.com")
    p.add_argument("--frontend", default="https://staging-student.ragab-seddik.com")
    p.add_argument("--json-report", type=Path, default=ROOT / "artifacts" / "v83-staging-bringup.json")
    args = p.parse_args()
    if not args.env_file.exists():
        print("NO-GO: staging env file not found", file=sys.stderr)
        return 2

    steps: list[dict] = []
    py = sys.executable
    steps.append(run_step("secret_readiness", [py, str(DEPLOY / "secret-readiness.py"), "--staging", str(args.env_file)]))
    infra_cmd = [py, str(DEPLOY / "infrastructure-validation.py"), "--env-file", str(args.env_file), "--label", "staging"]
    if args.write_canary:
        infra_cmd.append("--write-canary")
    steps.append(run_step("infrastructure_validation", infra_cmd))

    if args.phase in ("postdeploy", "full"):
        steps.append(run_step("dns_tls_readiness", [py, str(DEPLOY / "dns-tls-readiness.py"), "--api", args.api, "--frontend", args.frontend]))
        steps.append(run_step("staging_http_acceptance", ["sh", str(DEPLOY / "staging-acceptance.sh")]))

    failed = [s for s in steps if s["status"] == "FAIL"]
    report = {
        "version": "V83",
        "phase": args.phase,
        "timestamp": int(time.time()),
        "write_canary": bool(args.write_canary),
        "steps": steps,
        "go": not failed,
        "remaining_manual_gates": [
            "backup_restore_drill_on_disposable_database",
            "real_stream_tus_upload_and_playback",
            "paymob_test_mode_payment_and_webhook"],
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print("V83 STAGING BRING-UP")
    for s in steps:
        print(f"[{s['status']}] {s['name']}")
    print("GO" if not failed else "NO-GO")
    print(f"Report: {args.json_report}")
    return 0 if not failed else 1

if __name__ == "__main__":
    raise SystemExit(main())
