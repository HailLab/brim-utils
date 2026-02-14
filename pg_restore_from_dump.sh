#!/bin/bash
#
# Restores a pg_dump file into a Docker container, overwriting the existing database.
#
# Usage: pg_restore_from_dump.sh <DUMP_FILE> [CONTAINER_NAME] [DB_NAME] [DB_USER]
# Defaults: brim-db, summit_db, summit-db-user

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <DUMP_FILE> [CONTAINER_NAME] [DB_NAME] [DB_USER]"
    exit 1
fi

DUMP_FILE="$1"
CONTAINER_NAME="${2:-brim-db}"
DB_NAME="${3:-summit_db}"
DB_USER="${4:-summit-db-user}"
CONTAINER_DUMP="/tmp/$(basename "$DUMP_FILE")"

if [ ! -f "$DUMP_FILE" ]; then
    echo "Error: dump file not found: $DUMP_FILE"
    exit 1
fi

echo "[$(date -Iseconds)] Starting restore: file=${DUMP_FILE} container=${CONTAINER_NAME} db=${DB_NAME} user=${DB_USER}"

# Ensure container file is cleaned up even if something fails
trap 'docker exec "$CONTAINER_NAME" rm -f "$CONTAINER_DUMP" >/dev/null 2>&1 || true' EXIT

echo "Copying dump into container..."
docker cp "$DUMP_FILE" "$CONTAINER_NAME:$CONTAINER_DUMP"

echo "Terminating existing connections to ${DB_NAME}..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true

echo "Dropping and recreating database ${DB_NAME}..."
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";"
docker exec "$CONTAINER_NAME" psql -U "$DB_USER" -d postgres -c "CREATE DATABASE \"${DB_NAME}\" OWNER \"${DB_USER}\";"

echo "Restoring dump..."
docker exec "$CONTAINER_NAME" pg_restore -U "$DB_USER" -d "$DB_NAME" --no-owner --no-acl "$CONTAINER_DUMP"

echo "Cleaning up inside container..."
docker exec "$CONTAINER_NAME" rm -f "$CONTAINER_DUMP"

echo "Restore complete: ${DB_NAME} restored from ${DUMP_FILE}"
