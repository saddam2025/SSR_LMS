#!/usr/bin/env sh
set -eu

API_BASE="${STAGING_API_BASE:-https://staging-api.ragab-seddik.com}"
FRONTEND_BASE="${STAGING_FRONTEND_BASE:-https://staging-student.ragab-seddik.com}"
ORIGIN="${STAGING_FRONTEND_ORIGIN:-$FRONTEND_BASE}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 2; }; }
need curl

echo "[1/6] API health"
curl -fsS --max-time 15 "$API_BASE/health" >/dev/null

echo "[2/6] API readiness"
curl -fsS --max-time 15 "$API_BASE/ready" >/dev/null

echo "[3/6] Student frontend"
curl -fsS --max-time 15 "$FRONTEND_BASE/student/" >/dev/null

echo "[4/6] CORS credential preflight"
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT
curl -fsS -D "$headers" -o /dev/null --max-time 15 -X OPTIONS \
  -H "Origin: $ORIGIN" \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-CSRF-Token' \
  "$API_BASE/api/v1/session"
grep -qi "access-control-allow-origin: $ORIGIN" "$headers" || { echo 'CORS origin mismatch' >&2; exit 1; }
grep -qi 'access-control-allow-credentials: true' "$headers" || { echo 'CORS credentials missing' >&2; exit 1; }

echo "[5/6] Protected anonymous API contract"
status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 -H 'Accept: application/json' "$API_BASE/api/v1/session")"
[ "$status" = "401" ] || { echo "Expected anonymous /api/v1/session = 401, got $status" >&2; exit 1; }

echo "[6/6] Request ID"
headers2="$(mktemp)"
curl -fsS -D "$headers2" -o /dev/null --max-time 15 "$API_BASE/health"
grep -qi '^x-request-id:' "$headers2" || { rm -f "$headers2"; echo 'X-Request-ID missing' >&2; exit 1; }
rm -f "$headers2"

echo 'V81 STAGING ACCEPTANCE PASS'
