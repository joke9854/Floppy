#!/usr/bin/env bash
# Put the stable server on a released version (X.Y.Z).
#
#   stable-update.sh          newest released version
#   stable-update.sh 1.2.0    exactly that version (also how you go back)
#
# Writes FLOPPY_VERSION in ~/floppy/.env, backs the database up while Floppy is
# stopped (keeps the 5 newest db-backup-* folders), then starts the new
# version. Does nothing when stable already runs it, so it is safe from cron.
set -euo pipefail

STABLE_DIR=${FLOPPY_STABLE_DIR:-$HOME/floppy}
STABLE_SERVICE=${FLOPPY_STABLE_SERVICE:-floppy}
REPO=${FLOPPY_REPO:-joke9854/Floppy}
IMAGE=${FLOPPY_IMAGE:-ghcr.io/joke9854/floppy}
log() { echo "$(date -Is) $*"; }

exec 9>/tmp/floppy-stable-update.lock
flock -n 9 || exit 0

want=${1:-}
if [ -z "$want" ]; then
    command -v jq >/dev/null || { echo "jq is required (sudo apt install jq)." >&2; exit 1; }
    want=$(curl -fsSL -H "Accept: application/vnd.github+json" \
        ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
        "https://api.github.com/repos/$REPO/tags?per_page=100" |
        jq -r '.[].name' | grep -vE '^v2[0-9]\.' | sed -n 's/^v\([0-9]*\.[0-9]*\.[0-9]*\)$/\1/p' | sort -V | tail -n 1 || true)
    [ -n "$want" ] || { echo "No released version yet." >&2; exit 1; }
fi
want=${want#v}
if ! [[ "$want" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Versions look like 1.2.0, got: $want" >&2
    exit 1
fi

cd "$STABLE_DIR"
current=$(sed -n 's/^FLOPPY_VERSION=//p' .env 2>/dev/null || true)
[ "$current" = "$want" ] && exit 0

if ! docker pull --quiet "$IMAGE:$want" >/dev/null 2>&1; then
    log "image $want is not published yet (CI may still be building); stable unchanged"
    exit 0
fi

log "updating stable ${current:-unknown} -> $want"
if grep -q '^FLOPPY_VERSION=' .env; then
    sed -i "s/^FLOPPY_VERSION=.*/FLOPPY_VERSION=$want/" .env
else
    echo "FLOPPY_VERSION=$want" >>.env
fi

# Back up the database while Floppy is stopped, so the SQLite copy is consistent.
docker compose stop "$STABLE_SERVICE"
cp -a db "db-backup-$(date +%F-%H%M)"
ls -dt db-backup-* | tail -n +6 | xargs -r rm -rf

docker compose up -d --no-deps --force-recreate "$STABLE_SERVICE"
log "stable runs $want"
