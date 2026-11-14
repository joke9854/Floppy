#!/usr/bin/env bash
# Move the beta server to the newest CineTrack-API build whose CI passed.
#
# Does nothing while CI is still running, and leaves beta where it is when a
# check failed. Safe to run from cron, for example every 15 minutes:
#   */15 * * * * /path/to/deploy/stable-beta/beta-update.sh >> /path/to/beta-update.log 2>&1
#
# Needs curl and jq. Set GITHUB_TOKEN (read-only) to lift GitHub's anonymous
# rate limit of 60 requests an hour; this script makes 2 per run.
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE=${ENV_FILE:-beta.env}
REPO=${FLOPPY_REPO:-joke9854/Floppy}
BRANCH=${FLOPPY_BETA_BRANCH:-CineTrack-API}
command -v jq >/dev/null || { echo "jq is required (apt install jq)." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE." >&2; exit 1; }

api() {
    curl -fsSL -H "Accept: application/vnd.github+json" \
        ${GITHUB_TOKEN:+-H "Authorization: Bearer $GITHUB_TOKEN"} \
        "https://api.github.com/repos/$REPO/$1"
}

sha=$(api "commits/$BRANCH" | jq -r .sha)
runs=$(api "actions/runs?head_sha=$sha&per_page=50")
count() { jq "[.workflow_runs[] | select($1)] | length" <<<"$runs"; }

if [ "$(count '.status != "completed"')" -gt 0 ]; then
    echo "CI still running for ${sha:0:9}; beta unchanged."
    exit 0
fi
if [ "$(count '.conclusion != "success" and .conclusion != "skipped"')" -gt 0 ]; then
    echo "CI failed for ${sha:0:9}; beta unchanged."
    exit 0
fi
if [ "$(count '.name == "Docker Image" and .conclusion == "success"')" -eq 0 ] ||
   [ "$(count '.name == "CineTrack API Targeted Tests" and .conclusion == "success"')" -eq 0 ]; then
    echo "No green image and test run for ${sha:0:9} yet; beta unchanged."
    exit 0
fi

tag="sha-${sha:0:7}"
current=$(sed -n 's/^FLOPPY_BETA_TAG=//p' "$ENV_FILE")
if [ "$current" = "$tag" ]; then
    exit 0
fi

if grep -q '^FLOPPY_BETA_TAG=' "$ENV_FILE"; then
    sed -i "s/^FLOPPY_BETA_TAG=.*/FLOPPY_BETA_TAG=$tag/" "$ENV_FILE"
else
    echo "FLOPPY_BETA_TAG=$tag" >>"$ENV_FILE"
fi
docker compose -f docker-compose.beta.yml --env-file "$ENV_FILE" pull floppy-beta
docker compose -f docker-compose.beta.yml --env-file "$ENV_FILE" up -d floppy-beta
echo "$(date '+%Y-%m-%d %H:%M') beta moved from ${current:-none} to $tag."
