#!/bin/bash
# Daily backup: database dump + uploaded files, kept 30 days in /opt/ebfi/backups.
# Installed into cron by: (crontab -l 2>/dev/null; echo "15 2 * * * /opt/ebfi/app/deploy/backup.sh") | crontab -
set -e
cd "$(dirname "$0")/.."
DEST=/opt/ebfi/backups
mkdir -p "$DEST"
STAMP=$(date +%F)
docker compose exec -T db pg_dump -U ebfi -d ebfi --format=custom > "$DEST/db-$STAMP.dump"
docker compose run --rm --no-deps --user root -v "$DEST":/backup --entrypoint sh api -c "tar czf /backup/uploads-$STAMP.tgz -C /data uploads" >/dev/null
cp .env "$DEST/env-$STAMP.bak" && chmod 600 "$DEST/env-$STAMP.bak"
find "$DEST" -type f -mtime +30 -delete
echo "backup ok $STAMP"
