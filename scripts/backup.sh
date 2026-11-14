#!/usr/bin/env bash
# Daily PostgreSQL backup. Run from host cron, e.g.:
#   15 3 * * * cd /opt/sales-bot && ./scripts/backup.sh >> backups/backup.log 2>&1
# Optional off-site copy: set RCLONE_REMOTE (e.g. "b2:my-bucket/sales-bot") and configure rclone.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

KEEP_DAYS="${KEEP_DAYS:-30}"
mkdir -p backups
FILE="backups/salesbot_$(date +%Y-%m-%d_%H%M).sql.gz"

docker compose exec -T db pg_dump -U "${POSTGRES_USER:-salesbot}" -d "${POSTGRES_DB:-salesbot}" --no-owner \
  | gzip > "$FILE"
[ -s "$FILE" ] || { echo "backup is empty: $FILE"; exit 1; }
echo "$(date -Is) backup ok: $FILE ($(du -h "$FILE" | cut -f1))"

if [ -n "${RCLONE_REMOTE:-}" ]; then
  rclone copy "$FILE" "$RCLONE_REMOTE"
  echo "$(date -Is) uploaded to $RCLONE_REMOTE"
fi

find backups -name 'salesbot_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
