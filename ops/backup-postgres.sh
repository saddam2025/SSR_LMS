#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$OUT_DIR/mostashar-$STAMP.dump"
command -v pg_dump >/dev/null 2>&1 || { echo "pg_dump is required" >&2; exit 2; }
pg_dump --format=custom --no-owner --no-acl --file "$OUT" "$DATABASE_URL"
sha256sum "$OUT" > "$OUT.sha256"
echo "$OUT"
