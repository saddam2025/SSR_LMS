#!/usr/bin/env sh
set -eu

python -m app.preflight

if [ "${RUN_SEED_ON_START:-false}" = "true" ]; then
  python -m app.seed
fi

set -- uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --no-server-header \
  --workers "${WEB_CONCURRENCY:-1}" \
  --timeout-keep-alive "${UVICORN_KEEPALIVE_SECONDS:-5}" \
  --backlog "${UVICORN_BACKLOG:-2048}"

if [ "${TRUST_PROXY_HEADERS:-false}" = "true" ]; then
  set -- "$@" --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
fi

exec "$@"
