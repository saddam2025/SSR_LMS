#!/usr/bin/env sh
set -eu

ENV_FILE="${1:-}"
PHASE="${V83_PHASE:-predeploy}"
if [ -z "$ENV_FILE" ]; then
  echo "Usage: $0 /secure/path/staging.env" >&2
  exit 2
fi

EXTRA=""
if [ "${V83_R2_WRITE_CANARY:-false}" = "true" ]; then
  EXTRA="--write-canary"
fi

# shellcheck disable=SC2086
python deploy/staging-bringup.py --env-file "$ENV_FILE" --phase "$PHASE" $EXTRA
