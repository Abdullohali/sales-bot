#!/usr/bin/env bash
# Restore a backup into the running db container. DESTROYS current data.
#   ./scripts/restore.sh backups/salesbot_2026-11-12_0315.sql.gz
# Test this at least once on a staging server (restore that was never tested = no backup).
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
FILE="${1:?usage: restore.sh <backup.sql.gz>}"
U="${POSTGRES_USER:-salesbot}"; DB="${POSTGRES_DB:-salesbot}"

read -r -p "This will REPLACE database '$DB' with $FILE. Type 'yes' to continue: " ok
[ "$ok" = "yes" ] || exit 1

docker compose stop app
docker compose exec -T db psql -U "$U" -d postgres -c "DROP DATABASE IF EXISTS \"$DB\";" -c "CREATE DATABASE \"$DB\" OWNER \"$U\";"
gunzip -c "$FILE" | docker compose exec -T db psql -U "$U" -d "$DB" -v ON_ERROR_STOP=1 >/dev/null
docker compose start app
echo "restored $FILE"
