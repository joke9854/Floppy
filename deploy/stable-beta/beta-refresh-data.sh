#!/usr/bin/env bash
# Give the beta server a fresh copy of the stable data.
#
# Stable is only read: its database is snapshotted with SQLite's online backup
# (safe while stable keeps running) and copied, with stable's generated
# secret_key, into beta's own folder. Beta's previous database is kept as
# db.sqlite3.previous. When beta starts it pauses every connected-service
# schedule before anything else runs.
#
# Usage: beta-refresh-data.sh
set -euo pipefail

STABLE_DIR=${FLOPPY_STABLE_DIR:-$HOME/floppy}
BETA_DIR=${FLOPPY_BETA_DIR:-$HOME/floppy/beta}
STABLE_SERVICE=${FLOPPY_STABLE_SERVICE:-floppy}
beta() { docker compose --project-directory "$BETA_DIR" -f "$BETA_DIR/docker-compose.yml" "$@"; }

[ -f "$BETA_DIR/docker-compose.yml" ] || { echo "Run beta-setup.sh first." >&2; exit 1; }

# Refuse unless the beta service really runs in beta mode.
if ! beta config | grep -Eq 'FLOPPY_BETA_MODE: "?true"?'; then
    echo "$BETA_DIR/docker-compose.yml does not set FLOPPY_BETA_MODE=true; refusing." >&2
    exit 1
fi

stable=$(docker compose --project-directory "$STABLE_DIR" -f "$STABLE_DIR/docker-compose.yml" ps -q "$STABLE_SERVICE")
if [ -z "$stable" ]; then
    echo "Stable Floppy is not running (service $STABLE_SERVICE in $STABLE_DIR)." >&2
    exit 1
fi
if [ "$(docker inspect -f '{{.Name}}' "$stable")" = "/floppy-beta" ]; then
    echo "The stable service resolves to the beta container; refusing." >&2
    exit 1
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "Snapshotting the stable database (stable keeps running)..."
snapshot=$(docker exec -u abc "$stable" \
    python manage.py write_database_snapshot --dest /tmp/floppy-beta-copy | tail -n 1)
docker cp "$stable:$snapshot" "$tmp/db.sqlite3"
docker exec -u abc "$stable" rm -f "$snapshot"
docker cp "$stable:/floppy/db/secret_key" "$tmp/secret_key" 2>/dev/null || true

if ! head -c 16 "$tmp/db.sqlite3" | grep -q "SQLite format 3"; then
    echo "The snapshot is not a SQLite database; beta left unchanged." >&2
    exit 1
fi

echo "Stopping beta..."
beta stop floppy-beta >/dev/null 2>&1 || true

db="$BETA_DIR/data/db"
mkdir -p "$db"
for suffix in "" "-wal" "-shm"; do
    if [ -f "$db/db.sqlite3$suffix" ]; then
        mv -f "$db/db.sqlite3$suffix" "$db/db.sqlite3.previous$suffix"
    fi
done
cp "$tmp/db.sqlite3" "$db/db.sqlite3"
# Same key as stable, so beta can read the encrypted values in the copy.
if [ -f "$tmp/secret_key" ]; then
    cp "$tmp/secret_key" "$db/secret_key"
    chmod 600 "$db/secret_key"
fi

echo "Clearing beta's cache..."
beta up -d floppy-beta-redis >/dev/null
beta exec -T floppy-beta-redis redis-cli FLUSHALL >/dev/null

echo "Starting beta..."
beta up -d floppy-beta
echo "Done: beta runs on a copy of stable's data from $(date '+%Y-%m-%d %H:%M')."
