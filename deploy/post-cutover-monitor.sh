#!/usr/bin/env sh
set -eu
API_BASE="${PRODUCTION_API_BASE:-https://api.ragab-seddik.com}"
FRONTEND_BASE="${PRODUCTION_FRONTEND_BASE:-https://student.ragab-seddik.com}"
ITERATIONS="${V85_MONITOR_ITERATIONS:-6}"
INTERVAL="${V85_MONITOR_INTERVAL_SECONDS:-30}"
need(){ command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 2; }; }
need curl

i=1
fail=0
while [ "$i" -le "$ITERATIONS" ]; do
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  health="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$API_BASE/health" || true)"
  ready="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$API_BASE/ready" || true)"
  front="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$FRONTEND_BASE/student/" || true)"
  echo "$ts iteration=$i health=$health ready=$ready frontend=$front"
  [ "$health" = "200" ] || fail=1
  [ "$ready" = "200" ] || fail=1
  case "$front" in 2*|3*) : ;; *) fail=1;; esac
  i=$((i+1))
  [ "$i" -le "$ITERATIONS" ] && sleep "$INTERVAL"
done
[ "$fail" -eq 0 ] || { echo "V85 POST-CUTOVER MONITOR: FAIL" >&2; exit 1; }
echo "V85 POST-CUTOVER MONITOR: PASS"
