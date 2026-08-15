#!/usr/bin/env sh
set -eu
API_BASE="${PRODUCTION_API_BASE:-https://api.ragab-seddik.com}"
FRONTEND_BASE="${PRODUCTION_FRONTEND_BASE:-https://student.ragab-seddik.com}"
ORIGIN="${PRODUCTION_FRONTEND_ORIGIN:-$FRONTEND_BASE}"
need(){ command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 2; }; }
need curl

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT

echo '[1/9] API health + request ID'
curl -fsS -D "$tmp/api.headers" -o "$tmp/health.json" --max-time 20 "$API_BASE/health"
grep -qi '^x-request-id:' "$tmp/api.headers" || { echo 'X-Request-ID missing' >&2; exit 1; }

echo '[2/9] API readiness'
curl -fsS --max-time 20 "$API_BASE/ready" >/dev/null

echo '[3/9] Student frontend'
curl -fsS -D "$tmp/front.headers" -o /dev/null --max-time 20 "$FRONTEND_BASE/student/"

echo '[4/9] Frontend security headers'
grep -qi '^content-security-policy:' "$tmp/front.headers" || { echo 'Frontend CSP missing' >&2; exit 1; }
grep -qi '^x-content-type-options: *nosniff' "$tmp/front.headers" || { echo 'Frontend nosniff missing' >&2; exit 1; }

echo '[5/9] CORS credential preflight'
curl -fsS -D "$tmp/cors.headers" -o /dev/null --max-time 20 -X OPTIONS \
  -H "Origin: $ORIGIN" -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: X-CSRF-Token' "$API_BASE/api/v1/session"
grep -Fqi "access-control-allow-origin: $ORIGIN" "$tmp/cors.headers" || { echo 'CORS origin mismatch' >&2; exit 1; }
grep -qi 'access-control-allow-credentials: *true' "$tmp/cors.headers" || { echo 'CORS credentials missing' >&2; exit 1; }

echo '[6/9] Reject foreign CORS origin'
curl -sS -D "$tmp/bad-cors.headers" -o /dev/null --max-time 20 -X OPTIONS \
  -H 'Origin: https://evil.invalid' -H 'Access-Control-Request-Method: GET' "$API_BASE/api/v1/session" || true
if grep -Fqi 'access-control-allow-origin: https://evil.invalid' "$tmp/bad-cors.headers"; then echo 'Foreign CORS origin was allowed' >&2; exit 1; fi

echo '[7/9] Anonymous protected API contract'
status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 -H 'Accept: application/json' "$API_BASE/api/v1/session")"
[ "$status" = '401' ] || { echo "Expected 401, got $status" >&2; exit 1; }

echo '[8/9] HTTPS redirect / transport baseline'
case "$API_BASE" in https://*) : ;; *) echo 'Production API must be HTTPS' >&2; exit 1;; esac
case "$FRONTEND_BASE" in https://*) : ;; *) echo 'Production frontend must be HTTPS' >&2; exit 1;; esac

echo '[9/9] No server error on public roots'
for u in "$API_BASE/" "$FRONTEND_BASE/"; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$u" || true)"
  case "$code" in 5*) echo "Server error $code at $u" >&2; exit 1;; esac
done

echo 'V81 PRODUCTION ACCEPTANCE PASS'
