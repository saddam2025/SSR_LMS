#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:-.}"
export ENV=test
export APP_SECRET="${APP_SECRET:-test-secret-change-this}"
TMP="${TMPDIR:-/tmp}/mostashar-tests-$$"
mkdir -p "$TMP"
trap 'rm -rf "$TMP"' EXIT
pass=0
for t in tests/*.py; do
  name=$(basename "$t")
  [[ "$name" == "load_smoke.py" ]] && continue
  db="$TMP/${name%.py}.db"
  export DATABASE_URL="sqlite:///$db"
  echo "===== $t ====="
  python "$t"
  pass=$((pass+1))
done
echo "ALL ISOLATED PYTHON TESTS PASSED: $pass"
echo "Load smoke is intentionally separate and requires a running server: python tests/load_smoke.py"
