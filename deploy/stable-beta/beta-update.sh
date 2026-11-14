#!/usr/bin/env bash
# Move the beta server to the newest CineTrack-API build whose CI passed.
#
# Does nothing while CI is still running, and leaves beta where it is when a
# check failed. Safe to run from cron, for example every 15 minutes:
#   */15 * * * * $HOME/floppy/fork/deploy/stable-beta/beta-update.sh >> $HOME/floppy/beta/update.log 2>&1
#
# Needs curl and jq. Set GITHUB_TOKEN (read-only) to lift GitHub's anonymous
# rate limit of 60 requests an hour; this script makes 2 per run.
set -euo pipefail

BETA_DIR=${FLOPPY_BETA_DIR:-$HOME/floppy/beta}
REPO=${FLOPPY_REPO:-joke9854/Floppy}
BRANCH=${FLOPPY_BETA_BRANCH:-CineTrack-API}
command -v jq >/dev/null || { echo "jq is required (sudo apt install jq)." >&2; exit 1; }
[ -f "$BETA_DIR/.env" ] || { echo "Run beta-setup.sh first." >&2; exit 1; }

exec 9>/tmp/floppy-beta-update.lock
flock -n 9 || exit 0

api() {
    curl -fsSL -H "Accept: application/vnd.github+json" \
        ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
        "https://api.github.com/repos/$REPO/$1"
}

sha=$(api "commits/$BRANCH" | jq -r .sha)
runs=$(api "actions/runs?head_sha=$sha&per_page=50")
count() { jq "[.workflow_runs[] | select($1)] | length" <<<"$runs"; }

if [ "$(count '.status != "completed"')" -gt 0 ]; then
    exit 0
fi
if [ "$(count '.conclusion != "success" and .conclusion != "skipped"')" -gt 0 ]; then
    echo "$(date -Is) CI failed for ${sha:0:9}; beta unchanged."
    exit 0
fi
if [ "$(count '.name == "Docker Image" and .conclusion == "success"')" -eq 0 ] ||
   [ "$(count '.name == "CineTrack API Targeted Tests" and .conclusion == "success"')" -eq 0 ]; then
    exit 0
fi

tag="sha-${sha:0:7}"
current=$(sed -n 's/^FLOPPY_BETA_TAG=//p' "$BETA_DIR/.env")
[ "$current" = "$tag" ] && exit 0

if grep -q '^FLOPPY_BETA_TAG=' "$BETA_DIR/.env"; then
    sed -i "s/^FLOPPY_BETA_TAG=.*/FLOPPY_BETA_TAG=$tag/" "$BETA_DIR/.env"
else
    echo "FLOPPY_BETA_TAG=$tag" >>"$BETA_DIR/.env"
fi
cd "$BETA_DIR"
docker compose pull --quiet floppy-beta
docker compose up -d floppy-beta
version=$(docker image inspect "ghcr.io/joke9854/floppy:$tag" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' | sed -n 's/^VERSION=//p')
echo "$(date -Is) beta now runs ${version:-$tag} (${sha:0:9})."
