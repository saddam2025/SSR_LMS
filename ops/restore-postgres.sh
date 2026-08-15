#!/usr/bin/env sh
set -eu
: "${DATABASE_URL:?DATABASE_URL is required}"
: "${RESTORE_FILE:?RESTORE_FILE is required}"
[ "${CONFIRM_RESTORE:-}" = "YES_RESTORE_MOSTASHAR" ] || { echo "Set CONFIRM_RESTORE=YES_RESTORE_MOSTASHAR" >&2; exit 2; }
command -v pg_restore >/dev/null 2>&1 || { echo "pg_restore is required" >&2; exit 2; }
[ -f "$RESTORE_FILE" ] || { echo "Backup not found" >&2; exit 2; }
if [ -f "$RESTORE_FILE.sha256" ]; then sha256sum -c "$RESTORE_FILE.sha256"; fi
pg_restore --clean --if-exists --no-owner --no-acl --dbname "$DATABASE_URL" "$RESTORE_FILE"
echo "Restore complete"
