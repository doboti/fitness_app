#!/usr/bin/env bash
# Éjszakai mentés: konzisztens SQLite-másolat a konténerből + feltöltés S3-ba (ha be van állítva).
#
# crontab -e:
#   15 3 * * *  DATA_DIR=/út/a/workout-data /út/a/repóhoz/scripts/backup.sh >> /var/log/workout-backup.log 2>&1
#
# Beállítások (környezeti változóként vagy itt):
#   DATA_DIR   – a compose-ban /data-ra csatolt host mappa (pl. /opt/stack/workout-data)
#   S3_BUCKET  – pl. s3://sajat-workout-backup  (üresen hagyva csak helyi mentés készül)
#   KEEP       – ennyi helyi mentést tart meg (alapból 14)
set -euo pipefail

CONTAINER="${CONTAINER:-workout-api}"
DATA_DIR="${DATA_DIR:?Add meg a DATA_DIR-t (a /data-ra csatolt host mappa)}"
S3_BUCKET="${S3_BUCKET:-}"
KEEP="${KEEP:-14}"

echo "[$(date -Is)] mentés indul"
FILE_IN_CONTAINER="$(docker exec "$CONTAINER" python -m app.cli backup /data/backups --keep "$KEEP")"
FILE_ON_HOST="$DATA_DIR/backups/$(basename "$FILE_IN_CONTAINER")"
echo "helyi mentés: $FILE_ON_HOST ($(du -h "$FILE_ON_HOST" | cut -f1))"

if [[ -n "$S3_BUCKET" ]]; then
    aws s3 cp --only-show-errors --storage-class STANDARD_IA "$FILE_ON_HOST" "$S3_BUCKET/"
    echo "feltöltve: $S3_BUCKET/$(basename "$FILE_ON_HOST")"
fi
echo "[$(date -Is)] kész"
