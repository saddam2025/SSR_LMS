#!/usr/bin/env sh
set -eu
: "${ENV_FILE:?ENV_FILE must point to the deployment env file}"
LABEL="${LABEL:-environment}"
REPORT="${REPORT:-v82-infrastructure-report.json}"
if [ -n "${PRODUCTION_ENV_FILE:-}" ] && [ -n "${STAGING_ENV_FILE:-}" ]; then
  python3 deploy/secret-readiness.py --production "$PRODUCTION_ENV_FILE" --staging "$STAGING_ENV_FILE"
elif [ -n "${PRODUCTION_ENV_FILE:-}" ]; then
  python3 deploy/secret-readiness.py --production "$PRODUCTION_ENV_FILE"
elif [ -n "${STAGING_ENV_FILE:-}" ]; then
  python3 deploy/secret-readiness.py --staging "$STAGING_ENV_FILE"
fi
if [ "${R2_WRITE_CANARY:-false}" = "true" ]; then
  python3 deploy/infrastructure-validation.py --env-file "$ENV_FILE" --label "$LABEL" --json-report "$REPORT" --write-canary
else
  python3 deploy/infrastructure-validation.py --env-file "$ENV_FILE" --label "$LABEL" --json-report "$REPORT"
fi
printf '%s\n' 'V82 infrastructure gate PASS'
