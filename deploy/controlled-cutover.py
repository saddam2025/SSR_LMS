#!/usr/bin/env python3
"""V86 controlled cutover planner.

This is deliberately non-mutating. It consumes the V85 readiness report and emits
an operator command sheet only when V85 has GO_TO_CUTOVER_WINDOW.
"""
from __future__ import annotations
import argparse, json, time
from pathlib import Path

def load(p):
    try: return json.loads(p.read_text())
    except Exception: return {}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--v85-report", type=Path, required=True)
    ap.add_argument("--output", type=Path, default=Path("artifacts/v86-controlled-cutover.json"))
    args=ap.parse_args()
    v85=load(args.v85_report)
    ready=(v85.get("go") is True and v85.get("decision")=="GO_TO_CUTOVER_WINDOW")
    steps=[
      {"order":1,"action":"freeze_changes","command":"git/tag or immutable release reference; no source edits during cutover"},
      {"order":2,"action":"verify_release","command":"python deploy/verify-release-manifest.py"},
      {"order":3,"action":"fresh_database_backup","command":"ops/backup-postgres.sh"},
      {"order":4,"action":"deploy_backend","command":"npm ci && npm run check && npx wrangler deploy --config cloudflare/wrangler.production.jsonc"},
      {"order":5,"action":"deploy_student_pages","command":"python deploy/build-pages.py --environment production, then deploy generated Pages artifact"},
      {"order":6,"action":"production_acceptance","command":"sh deploy/production-acceptance.sh"},
      {"order":7,"action":"observation_window","command":"sh deploy/post-cutover-monitor.sh"},
      {"order":8,"action":"first_user_acceptance","command":"record controlled student login/course/protected-video/logout evidence"},
    ]
    report={"version":"V86","timestamp":int(time.time()),"source_v85_go":ready,
            "decision":"CUTOVER_COMMAND_SHEET_READY" if ready else "NO_GO_DO_NOT_CUTOVER",
            "steps":steps if ready else [],
            "safety":{"dns_changed":False,"deployment_performed":False,"secrets_printed":False}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n")
    print(report["decision"])
    print(args.output)
    return 0 if ready else 1
if __name__=="__main__": raise SystemExit(main())
