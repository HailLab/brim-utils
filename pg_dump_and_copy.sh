#!/bin/bash
#
## Crontab example:
# 0 0 * * * /path/to/pg_dump_and_copy.sh brim-db summit_db summit-db-user 14 >> /path/to/logs.txt 2>&1
#
# Args: [CONTAINER_NAME] [DB_NAME] [DB_USER] [RETENTION_DAYS]
# Defaults: brim-db, summit_db, summit-db-user, 14

set -euo pipefail

CONTAINER_NAME="${1:-brim-db}"
DB_NAME="${2:-summit_db}"
DB_USER="${3:-summit-db-user}"
RETENTION_DAYS="${4:-14}"
BACKUP_DIR="${BACKUP_DIR:-pg_dumps}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
DUMP_FILE="/tmp/${DB_NAME}_${TIMESTAMP}.dump"

echo "[$(date -Iseconds)] Starting backup: container=${CONTAINER_NAME} db=${DB_NAME} user=${DB_USER} retention_days=${RETENTION_DAYS}"

# Ensure container file is cleaned up even if something fails
trap 'docker exec "$CONTAINER_NAME" sh -c "[ -f \"$DUMP_FILE\" ] && rm -f \"$DUMP_FILE\"" >/dev/null 2>&1 || true' EXIT

echo "Creating dump inside container..."
docker exec "$CONTAINER_NAME" pg_dump -Fc -U "$DB_USER" "$DB_NAME" -f "$DUMP_FILE"

echo "Copying dump to host..."
mkdir -p "$BACKUP_DIR"
docker cp "$CONTAINER_NAME:$DUMP_FILE" "$BACKUP_DIR/"

echo "Cleaning up inside container..."
docker exec "$CONTAINER_NAME" rm -f "$DUMP_FILE"

# Prune old backups
echo "Pruning backups older than ${RETENTION_DAYS} day(s) in ${BACKUP_DIR}..."
find "$BACKUP_DIR" -maxdepth 1 -type f -name "${DB_NAME}_*.dump" -mtime +"$RETENTION_DAYS" -print -delete

echo "Backup complete: ${BACKUP_DIR}/${DB_NAME}_${TIMESTAMP}.dump"
