#!/usr/bin/env bash
# Switch the beta server to Postgres (v2 P2-A trial), or back to SQLite.
#
#   beta-use-postgres.sh        add a Postgres service to beta and restart it;
#                               beta copies its current db.sqlite3 into the
#                               empty Postgres at start (the SQLite file stays)
#   beta-use-postgres.sh --off  remove the Postgres service from beta's stack
#                               and restart on db.sqlite3; the Postgres data
#                               stays in data/postgres until removed by hand
#
# Only beta is touched. Stable is never read or changed by this script.
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
BETA_DIR=${FLOPPY_BETA_DIR:-$HOME/floppy/beta}
override="$BETA_DIR/docker-compose.override.yml"

[ -f "$BETA_DIR/docker-compose.yml" ] || { echo "Run beta-setup.sh first." >&2; exit 1; }
cd "$BETA_DIR"
if ! docker compose -f docker-compose.yml config | grep -Eq 'FLOPPY_BETA_MODE: "?true"?'; then
    echo "$BETA_DIR/docker-compose.yml does not set FLOPPY_BETA_MODE=true; refusing." >&2
    exit 1
fi

if [ "${1:-}" = "--off" ]; then
    [ -f "$override" ] || { echo "Beta already runs on SQLite."; exit 0; }
    docker compose stop floppy-beta floppy-beta-db >/dev/null 2>&1 || true
    docker compose rm -f floppy-beta-db >/dev/null 2>&1 || true
    rm -f "$override"
    docker compose up -d floppy-beta
    echo "Beta runs on SQLite again. Postgres data kept in $BETA_DIR/data/postgres."
    exit 0
fi

# A password only beta's two containers know, kept in beta's .env (mode 600).
if ! grep -q '^BETA_DB_PASSWORD=' .env; then
    umask 077
    password=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom 2>/dev/null | head -c 32 || true)
    [ "${#password}" -eq 32 ] || { echo "Could not generate a password." >&2; exit 1; }
    printf '\n# Beta Postgres password (beta-use-postgres.sh)\nBETA_DB_PASSWORD=%s\n' \
        "$password" >>.env
    chmod 600 .env
fi

# An image without the copy step would start on the empty Postgres. Ask the
# running beta: the command answers 0 (copy due) or 3 (not due), and is
# missing from images that predate it.
copy_check=0
docker compose -f docker-compose.yml exec -T -u abc floppy-beta \
    python manage.py copy_sqlite_to_postgres --needed >/dev/null 2>&1 || copy_check=$?
if [ "$copy_check" -ne 0 ] && [ "$copy_check" -ne 3 ]; then
    echo "Beta's image cannot copy SQLite to Postgres (or beta is not running)." >&2
    echo "Let beta-update.sh bring it to a current build first; nothing changed." >&2
    exit 1
fi

# Check the stack with the override before installing it, so a bad file
# never reaches the cron beta-update.sh.
if ! docker compose -f docker-compose.yml -f "$here/docker-compose.beta-postgres.yml" \
    config >/dev/null; then
    echo "The Postgres override does not combine with beta's stack; nothing changed." >&2
    exit 1
fi
mkdir -p data/postgres
cp "$here/docker-compose.beta-postgres.yml" "$override"

echo "Starting beta on Postgres; the first start copies db.sqlite3 into it..."
docker compose up -d floppy-beta
echo "Follow the copy with: docker compose -f $BETA_DIR/docker-compose.yml -f $override logs -f floppy-beta"
