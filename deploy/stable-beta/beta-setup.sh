#!/usr/bin/env bash
# One-time setup of the beta server next to an existing stable Floppy.
#
# Creates ~/floppy/beta with docker-compose.yml, .env and floppy.env (a copy of
# stable's floppy.env with the beta address), then you run
# beta-refresh-data.sh to give it a copy of the data and start it.
#
# Usage: beta-setup.sh https://beta.example.com
#   FLOPPY_STABLE_DIR (default ~/floppy) and FLOPPY_BETA_DIR (default
#   ~/floppy/beta) change the folders.
set -euo pipefail

beta_url=${1:?usage: beta-setup.sh <beta address, e.g. https://beta.example.com>}
here=$(cd "$(dirname "$0")" && pwd)
STABLE_DIR=${FLOPPY_STABLE_DIR:-$HOME/floppy}
BETA_DIR=${FLOPPY_BETA_DIR:-$HOME/floppy/beta}

if [ -e "$BETA_DIR/docker-compose.yml" ]; then
    echo "$BETA_DIR is already set up; edit its files instead." >&2
    exit 1
fi
if [ ! -f "$STABLE_DIR/floppy.env" ]; then
    echo "No $STABLE_DIR/floppy.env to copy settings from (set FLOPPY_STABLE_DIR)." >&2
    exit 1
fi

mkdir -p "$BETA_DIR/data/db" "$BETA_DIR/data/backups" "$BETA_DIR/data/redis"
cp "$here/docker-compose.beta.yml" "$BETA_DIR/docker-compose.yml"
cat >"$BETA_DIR/.env" <<'EOF'
# Image tag beta runs; beta-update.sh keeps it on the newest green build.
FLOPPY_BETA_TAG=beta
# Host port for beta (stable uses 8000).
BETA_PORT=8001
EOF

# Floppy's settings: stable's, with the beta address. REDIS_URL, beta mode and
# the Sentry environment are forced by docker-compose.yml.
umask 077
sed -E "/^URLS=/d" "$STABLE_DIR/floppy.env" >"$BETA_DIR/floppy.env"
printf '\n# Beta address\nURLS=%s\n' "$beta_url" >>"$BETA_DIR/floppy.env"

echo "Beta folder ready: $BETA_DIR"
echo "Next: add the tunnel hostname, then run $here/beta-refresh-data.sh"
