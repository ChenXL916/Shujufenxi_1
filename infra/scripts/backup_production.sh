#!/usr/bin/env bash
set -euo pipefail
umask 077

PROJECT_DIR=${LIVEOPS_PROJECT_DIR:-/opt/live-ops/current}
BACKUP_DIR=${LIVEOPS_BACKUP_DIR:-/mnt/d/LiveOps/backups/postgres}
RETENTION_COUNT=${LIVEOPS_BACKUP_RETENTION_COUNT:-14}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
BACKUP_PATH="${BACKUP_DIR}/live_ops-${STAMP}.dump"

install -d -m 0700 "$BACKUP_DIR"
cd "$PROJECT_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  sh -lc 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$BACKUP_PATH"
test -s "$BACKUP_PATH"
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres \
  pg_restore --list < "$BACKUP_PATH" > /dev/null
sha256sum "$BACKUP_PATH" > "${BACKUP_PATH}.sha256"

mapfile -t BACKUPS < <(printf '%s\n' "$BACKUP_DIR"/live_ops-*.dump | sort -r)
for ((INDEX=RETENTION_COUNT; INDEX<${#BACKUPS[@]}; INDEX++)); do
  rm -f "${BACKUPS[$INDEX]}" "${BACKUPS[$INDEX]}.sha256"
done

printf 'BACKUP=PASS path=%s bytes=%s\n' "$BACKUP_PATH" "$(stat -c %s "$BACKUP_PATH")"
