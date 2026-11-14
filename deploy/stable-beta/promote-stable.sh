#!/usr/bin/env bash
# Promote a commit you tried on beta to the stable branch.
#
# Run it from a Floppy checkout on your PC (needs git and gh, signed in).
# The commit must be on CineTrack-API and every CI run for it must be green.
# CI then builds ghcr.io/joke9854/floppy:stable from exactly that commit.
#
# Usage: deploy/stable-beta/promote-stable.sh <commit>
#        ROLLBACK=1 deploy/stable-beta/promote-stable.sh <older commit>
set -euo pipefail

target=${1:?usage: promote-stable.sh <commit>}
REPO=${FLOPPY_REPO:-joke9854/Floppy}

git fetch --quiet origin CineTrack-API
git fetch --quiet origin stable 2>/dev/null || true
sha=$(git rev-parse --verify "${target}^{commit}")

if ! git merge-base --is-ancestor "$sha" origin/CineTrack-API; then
    echo "${sha:0:9} is not on CineTrack-API; only commits that went through beta can be promoted." >&2
    exit 1
fi

states=$(gh api "repos/$REPO/actions/runs?head_sha=$sha&per_page=50" \
    --jq '.workflow_runs[] | "\(.name)\t\(.status)\t\(.conclusion)"')
if [ -z "$states" ] || echo "$states" | awk -F'\t' '$2 != "completed" || ($3 != "success" && $3 != "skipped") {bad=1} END {exit !bad}'; then
    echo "CI for ${sha:0:9} is missing, still running or not green:" >&2
    echo "${states:-  (no runs)}" >&2
    exit 1
fi

if git rev-parse --verify --quiet origin/stable >/dev/null; then
    old=$(git rev-parse origin/stable)
    if ! git merge-base --is-ancestor "$old" "$sha"; then
        if [ "${ROLLBACK:-0}" != "1" ]; then
            echo "stable (${old:0:9}) is not an ancestor of ${sha:0:9}. To roll back on purpose, run again with ROLLBACK=1." >&2
            exit 1
        fi
        git push --force-with-lease="stable:$old" origin "$sha:refs/heads/stable"
        echo "stable rolled back to ${sha:0:9}; CI is building :stable."
        exit 0
    fi
fi

git push origin "$sha:refs/heads/stable"
echo "stable is now ${sha:0:9}; CI is building :stable. Update the server when it is green."
