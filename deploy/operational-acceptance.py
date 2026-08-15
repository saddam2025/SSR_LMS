#!/usr/bin/env python3
"""V84 staging operational acceptance aggregator.

Combines automated V83 bring-up with explicit evidence files for manual/unsafe-to-auto gates.
Never prints secrets. Produces one machine-readable Go/No-Go report.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / 'deploy'
REQUIRED_EVIDENCE = ('stream_tus', 'backup_restore', 'paymob_test')


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('evidence must be a JSON object')
        return data
    except Exception as exc:
        return {'go': False, 'error': f'{type(exc).__name__}: invalid evidence file'}


def validate_evidence(kind: str, path: Path | None) -> dict:
    if path is None:
        return {'name': kind, 'status': 'FAIL', 'detail': 'evidence file not provided'}
    if not path.exists():
        return {'name': kind, 'status': 'FAIL', 'detail': 'evidence file not found'}
    data = load_json(path)
    if not data.get('go'):
        return {'name': kind, 'status': 'FAIL', 'detail': data.get('summary') or data.get('error') or 'evidence reports NO-GO'}
    expected = {
        'stream_tus': ('upload_resumable', 'playback_ok', 'authorization_ok'),
        'backup_restore': ('backup_created', 'restore_completed', 'integrity_verified'),
        'paymob_test': ('payment_success', 'webhook_verified', 'subscription_activated'),
    }[kind]
    missing = [k for k in expected if data.get(k) is not True]
    if missing:
        return {'name': kind, 'status': 'FAIL', 'detail': 'missing PASS assertions: ' + ', '.join(missing)}
    return {'name': kind, 'status': 'PASS', 'detail': 'evidence validated', 'evidence_timestamp': data.get('timestamp')}


def run_v83(env_file: Path, write_canary: bool) -> tuple[dict, str]:
    report = ROOT / 'artifacts' / 'v84-v83-full.json'
    cmd = [sys.executable, str(DEPLOY / 'staging-bringup.py'), '--env-file', str(env_file), '--phase', 'full', '--json-report', str(report)]
    if write_canary:
        cmd.append('--write-canary')
    proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=420)
    out = (proc.stdout + proc.stderr).strip()
    if len(out) > 6000:
        out = out[-6000:]
    data = load_json(report) if report.exists() else {'go': False}
    return data, out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--env-file', type=Path, required=True)
    ap.add_argument('--stream-evidence', type=Path)
    ap.add_argument('--backup-evidence', type=Path)
    ap.add_argument('--paymob-evidence', type=Path)
    ap.add_argument('--write-canary', action='store_true')
    ap.add_argument('--json-report', type=Path, default=ROOT / 'artifacts' / 'v84-operational-acceptance.json')
    args = ap.parse_args()

    if not args.env_file.exists():
        print('NO-GO: staging env file not found', file=sys.stderr)
        return 2

    v83, v83_output = run_v83(args.env_file, args.write_canary)
    checks = [{
        'name': 'automated_staging_bringup',
        'status': 'PASS' if v83.get('go') else 'FAIL',
        'detail': 'V83 full bring-up passed' if v83.get('go') else 'V83 full bring-up failed',
    }]
    checks.append(validate_evidence('stream_tus', args.stream_evidence))
    checks.append(validate_evidence('backup_restore', args.backup_evidence))
    checks.append(validate_evidence('paymob_test', args.paymob_evidence))

    failed = [c for c in checks if c['status'] == 'FAIL']
    report = {
        'version': 'V84',
        'timestamp': int(time.time()),
        'environment': 'staging',
        'checks': checks,
        'go': not failed,
        'automated_bringup_report': v83,
        'automated_bringup_log_tail': v83_output,
        'next_gate': 'production_cutover_review' if not failed else 'remain_on_staging',
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')

    print('V84 STAGING OPERATIONAL ACCEPTANCE')
    for c in checks:
        print(f"[{c['status']}] {c['name']}: {c['detail']}")
    print('GO' if not failed else 'NO-GO')
    print(f'Report: {args.json_report}')
    return 0 if not failed else 1

if __name__ == '__main__':
    raise SystemExit(main())
