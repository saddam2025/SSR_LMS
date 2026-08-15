#!/usr/bin/env sh
set -eu

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL is required and MUST point to a disposable drill database}"

case "$RESTORE_DATABASE_URL" in
  "$DATABASE_URL") echo 'Refusing restore drill: source and target DATABASE_URL are identical' >&2; exit 2 ;;
esac

command -v pg_dump >/dev/null 2>&1 || { echo 'pg_dump is required' >&2; exit 2; }
command -v pg_restore >/dev/null 2>&1 || { echo 'pg_restore is required' >&2; exit 2; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
file="$work/mostashar-v81-drill.dump"

echo '[1/3] Creating production-format logical backup'
pg_dump --format=custom --no-owner --no-acl --dbname="$DATABASE_URL" --file="$file"
test -s "$file"

echo '[2/3] Restoring into disposable drill database'
pg_restore --clean --if-exists --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" "$file"

echo '[3/3] Verifying restored schema has tables'
count="$(psql "$RESTORE_DATABASE_URL" -Atc "select count(*) from information_schema.tables where table_schema='public';")"
[ "${count:-0}" -gt 0 ] || { echo 'Restore drill failed: no public tables' >&2; exit 1; }

echo "V81 BACKUP/RESTORE DRILL PASS ($count public tables)"
