#!/usr/bin/env bash
# Give the beta server a fresh copy of the stable data.
#
# Stable is only read: its database is snapshotted with SQLite's online backup
# (safe while stable keeps running) and copied into beta's own folder. Beta's
# previous database is kept as db.sqlite3.previous. When beta starts it pauses
# every connected-service schedule before anything else runs.
#
# Usage: ./beta-refresh-data.sh            (reads beta.env next to this file)
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=${ENV_FILE:-beta.env}
if [ ! -f "$ENV_FILE" ]; then
    echo "Missing $ENV_FILE: copy beta.env.example to $ENV_FILE and fill it in." >&2
    exit 1
fi
set -a
# shellcheck disable=SC1090
. "./$ENV_FILE"
set +a

STABLE_CONTAINER=${STABLE_CONTAINER:-floppy}
BETA_DATA_DIR=${BETA_DATA_DIR:-./beta}
compose() { docker compose -f docker-compose.beta.yml --env-file "$ENV_FILE" "$@"; }

# Refuse unless the beta service really runs in beta mode.
if ! compose config | grep -Eq 'FLOPPY_BETA_MODE: "?true"?'; then
    echo "docker-compose.beta.yml does not set FLOPPY_BETA_MODE=true; refusing." >&2
    exit 1
fi
if [ "$STABLE_CONTAINER" = "floppy-beta" ]; then
    echo "STABLE_CONTAINER points at the beta container; refusing." >&2
    exit 1
fi
if ! docker inspect "$STABLE_CONTAINER" >/dev/null 2>&1; then
    echo "No container named $STABLE_CONTAINER: set STABLE_CONTAINER in $ENV_FILE (see docker ps)." >&2
    exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Snapshotting the stable database (stable keeps running)..."
snapshot=$(docker exec -u abc "$STABLE_CONTAINER" \
    python manage.py write_database_snapshot --dest /tmp/floppy-beta-copy | tail -n 1)
docker cp "$STABLE_CONTAINER:$snapshot" "$tmp/db.sqlite3"
docker exec -u abc "$STABLE_CONTAINER" rm -f "$snapshot"

if ! head -c 16 "$tmp/db.sqlite3" | grep -q "SQLite format 3"; then
    echo "The snapshot is not a SQLite database; beta left unchanged." >&2
    exit 1
fi

echo "Stopping beta..."
compose stop floppy-beta >/dev/null 2>&1 || true

mkdir -p "$BETA_DATA_DIR/db" "$BETA_DATA_DIR/backups"
for suffix in "" "-wal" "-shm"; do
    if [ -f "$BETA_DATA_DIR/db/db.sqlite3$suffix" ]; then
        mv -f "$BETA_DATA_DIR/db/db.sqlite3$suffix" "$BETA_DATA_DIR/db/db.sqlite3.previous$suffix"
    fi
done
cp "$tmp/db.sqlite3" "$BETA_DATA_DIR/db/db.sqlite3"

echo "Clearing beta's cache..."
compose up -d floppy-beta-redis >/dev/null
compose exec -T floppy-beta-redis redis-cli FLUSHALL >/dev/null

echo "Starting beta..."
compose up -d floppy-beta
echo "Done: beta now runs on a copy of stable's data from $(date '+%Y-%m-%d %H:%M')."
