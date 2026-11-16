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

mkdir -p data/postgres
cp "$here/docker-compose.beta-postgres.yml" "$override"
docker compose config >/dev/null

echo "Starting beta on Postgres; the first start copies db.sqlite3 into it..."
docker compose up -d floppy-beta
echo "Follow the copy with: docker compose -f $BETA_DIR/docker-compose.yml -f $override logs -f floppy-beta"
