#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
export PYTHONPATH="${PYTHONPATH:-.}"
export ENV="${ENV:-test}"
export APP_SECRET="${APP_SECRET:-test-secret-change-this}"

python -m compileall -q app tests
python release_check.py
bash run-all-tests-isolated.sh

echo "$(cat VERSION) RELEASE GATE OK"
