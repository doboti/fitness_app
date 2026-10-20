#!/usr/bin/env bash
# PROD telepítés az Optiplexen.
#
# A CI (Deploy PROD workflow) SSH-n hívja kötött parancsként (authorized_keys: command="…/deploy.sh"),
# ilyenkor a commit-azonosító az SSH_ORIGINAL_COMMAND-ban érkezik. Kézzel is futtatható:
#     /srv/workout/app/scripts/deploy.sh <40 karakteres commit-sha>
#
# Lépések: git checkout → adatbázis-mentés → docker build + újraindítás → állapot-ellenőrzés → hiba esetén visszaállás.
set -euo pipefail

APP_DIR="${APP_DIR:-/srv/workout/app}"            # a repó klónja
DATA_DIR="${WORKOUT_DATA_DIR:-/srv/workout/data}"  # az SQLite adatbázis és a mentések (a konténer /data-ja)
STATE_FILE="${STATE_FILE:-/srv/workout/DEPLOYED_COMMIT}"
PROJECT="workout"
HEALTH_URL="http://127.0.0.1:8420/api/health"

# A checkout ezt a fájlt is felülírja, ezért egy ideiglenes másolatból futunk tovább.
if [[ -z "${DEPLOY_REEXEC:-}" ]]; then
    tmp="$(mktemp)"
    cp "$0" "$tmp"
    DEPLOY_REEXEC=1 exec bash "$tmp" "$@"
fi
trap 'rm -f "$0"' EXIT

log() { echo "[$(date '+%F %T')] $*"; }

SHA="${1:-${SSH_ORIGINAL_COMMAND:-}}"
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
    echo "Hibás vagy hiányzó commit-azonosító: '${SHA}'" >&2
    exit 2
fi

cd "$APP_DIR"
PREVIOUS="$(cat "$STATE_FILE" 2>/dev/null || true)"

log "Kód letöltése (${SHA:0:12})"
git fetch --quiet --prune origin '+refs/heads/*:refs/remotes/origin/*'
if ! git cat-file -e "${SHA}^{commit}" 2>/dev/null; then
    echo "A commit nincs a repóban: $SHA" >&2
    exit 3
fi
git checkout --quiet --force --detach "$SHA"

export WORKOUT_DATA_DIR="$DATA_DIR"
compose() { docker compose -p "$PROJECT" -f "$APP_DIR/docker-compose.yml" "$@"; }

if [[ -n "$(docker ps -q -f name='^workout-api$')" ]]; then
    log "Adatbázis-mentés telepítés előtt"
    docker exec workout-api python -m app.cli backup /data/backups --keep 30 || log "FIGYELEM: a mentés nem sikerült"
fi
if docker image inspect workout-api:latest >/dev/null 2>&1; then
    docker tag workout-api:latest workout-api:previous
fi

log "Build és újraindítás"
compose up -d --build --remove-orphans

log "Állapot-ellenőrzés"
for _ in $(seq 1 30); do
    if curl -fsS --max-time 3 "$HEALTH_URL" >/dev/null 2>&1; then
        echo "$SHA" > "$STATE_FILE"
        log "Kész: ${SHA:0:12} fut a PROD-on."
        docker image prune -f >/dev/null 2>&1 || true   # a régi, már nem használt build-rétegek törlése
        exit 0
    fi
    sleep 2
done

log "HIBA: az új verzió nem indult el – visszaállás az előzőre"
docker logs --tail 60 workout-api 2>&1 || true
if docker image inspect workout-api:previous >/dev/null 2>&1; then
    [[ -n "$PREVIOUS" ]] && git checkout --quiet --force --detach "$PREVIOUS"
    docker tag workout-api:previous workout-api:latest
    compose up -d --no-build
    log "Visszaállítva: ${PREVIOUS:0:12}"
fi
exit 1
