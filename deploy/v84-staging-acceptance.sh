#!/usr/bin/env sh
set -eu
ENV_FILE="${1:-}"
EVIDENCE_DIR="${2:-artifacts/evidence}"
if [ -z "$ENV_FILE" ]; then
  echo "Usage: $0 /secure/staging.env [evidence-dir]" >&2
  exit 2
fi
EXTRA=""
if [ "${V84_R2_WRITE_CANARY:-false}" = "true" ]; then
  EXTRA="--write-canary"
fi
# shellcheck disable=SC2086
python deploy/operational-acceptance.py \
  --env-file "$ENV_FILE" \
  --stream-evidence "$EVIDENCE_DIR/stream-tus.json" \
  --backup-evidence "$EVIDENCE_DIR/backup-restore.json" \
  --paymob-evidence "$EVIDENCE_DIR/paymob-test.json" \
  $EXTRA
