#!/bin/sh
# Deploy the CineTrack-API image only when its exact commit passed CI.
#
# Run from the directory that holds the server's compose file:
#   ./deploy_cinetrack.sh
# It pulls the image, reads the commit baked into it, and refuses to restart
# unless that commit's "CineTrack API Targeted Tests" run succeeded. Each
# deploy is appended to deployments.log with the commit and the CI run URL.
#
# Overrides: FLOPPY_IMAGE, FLOPPY_REPO, FLOPPY_DEPLOY_LOG.
set -eu

IMAGE="${FLOPPY_IMAGE:-ghcr.io/joke9854/floppy:cinetrack-api}"
REPO="${FLOPPY_REPO:-joke9854/Floppy}"
LOG="${FLOPPY_DEPLOY_LOG:-deployments.log}"
WORKFLOW="CineTrack API Targeted Tests"

docker pull "$IMAGE"
sha=$(docker image inspect "$IMAGE" \
    --format '{{range .Config.Env}}{{println .}}{{end}}' |
    sed -n 's/^COMMIT_SHA=//p')
if [ -z "$sha" ]; then
    echo "Refusing to deploy: $IMAGE carries no COMMIT_SHA." >&2
    exit 1
fi

# The newest run of the workflow for this commit: "<conclusion> <url>".
result=$(curl -fsS \
    "https://api.github.com/repos/$REPO/actions/runs?head_sha=$sha&per_page=100" |
    WORKFLOW="$WORKFLOW" python3 -c '
import json, os, sys
runs = [r for r in json.load(sys.stdin)["workflow_runs"]
        if r["name"] == os.environ["WORKFLOW"]]
if not runs:
    print("missing -")
else:
    run = max(runs, key=lambda r: r["created_at"])
    print(run["conclusion"] or run["status"], run["html_url"])
')
conclusion=${result%% *}
run_url=${result#* }

if [ "$conclusion" != "success" ]; then
    echo "Refusing to deploy $sha: \"$WORKFLOW\" is $conclusion ($run_url)." >&2
    exit 1
fi

docker compose up -d
printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$sha" "$IMAGE" "$run_url" >>"$LOG"
echo "Deployed $sha; CI: $run_url"
