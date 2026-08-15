#!/usr/bin/env sh
set -eu
V84_REPORT="${1:-artifacts/v84-operational-acceptance.json}"
PROD_ENV="${2:-}"
EVIDENCE_DIR="${3:-artifacts/production-evidence}"
if [ -z "$PROD_ENV" ]; then
  echo "Usage: $0 <v84-report> /secure/production.env [production-evidence-dir]" >&2
  exit 2
fi
python deploy/production-cutover-readiness.py \
  --v84-report "$V84_REPORT" \
  --production-env "$PROD_ENV" \
  --rollback-evidence "$EVIDENCE_DIR/rollback-plan.json" \
  --first-user-evidence "$EVIDENCE_DIR/first-user.json" \
  --monitoring-evidence "$EVIDENCE_DIR/monitoring.json"
