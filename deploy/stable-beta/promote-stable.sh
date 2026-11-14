#!/usr/bin/env bash
# Release a commit you tried on beta as a stable version X.Y.Z.
#
# Run it from a Floppy checkout on your PC (needs git and gh, signed in).
# The commit must be on CineTrack-API and every CI run for it must be green.
# It tags the commit vX.Y.Z, moves the stable branch there and pushes both;
# CI then builds ghcr.io/joke9854/floppy:X.Y.Z and :stable.
#
# Usage: deploy/stable-beta/promote-stable.sh <commit> [patch|minor|major|X.Y.Z]
#        (default: patch, e.g. 1.2.0 -> 1.2.1)
set -euo pipefail

target=${1:?usage: promote-stable.sh <commit> [patch|minor|major|X.Y.Z]}
bump=${2:-patch}
REPO=${FLOPPY_REPO:-joke9854/Floppy}

git fetch --quiet --tags origin CineTrack-API
git fetch --quiet origin stable 2>/dev/null || true
sha=$(git rev-parse --verify "${target}^{commit}")

if ! git merge-base --is-ancestor "$sha" origin/CineTrack-API; then
    echo "${sha:0:9} is not on CineTrack-API; only commits that went through beta can be released." >&2
    exit 1
fi

states=$(gh api "repos/$REPO/actions/runs?head_sha=$sha&per_page=50" \
    --jq '.workflow_runs[] | "\(.name)\t\(.status)\t\(.conclusion)"')
if [ -z "$states" ] || echo "$states" | awk -F'\t' '$2 != "completed" || ($3 != "success" && $3 != "skipped") {bad=1} END {exit !bad}'; then
    echo "CI for ${sha:0:9} is missing, still running or not green:" >&2
    echo "${states:-  (no runs)}" >&2
    exit 1
fi

# Our releases only: vX.Y.Z tags (upstream's date tags are never pushed here).
last=$(git tag -l 'v*' | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | grep -vE '^v2[0-9]\.' | sed 's/^v//' | sort -V | tail -n 1)
last=${last:-0.0.0}
IFS=. read -r major minor patch <<<"$last"
case "$bump" in
    patch) version="$major.$minor.$((patch + 1))" ;;
    minor) version="$major.$((minor + 1)).0" ;;
    major) version="$((major + 1)).0.0" ;;
    *) version=${bump#v} ;;
esac
if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Versions look like 1.2.0, got: $version" >&2
    exit 1
fi
if [ "$(printf '%s\n%s\n' "$last" "$version" | sort -V | tail -n 1)" != "$version" ] || [ "$last" = "$version" ]; then
    echo "$version is not newer than the last release $last." >&2
    exit 1
fi
if git rev-parse --verify --quiet "refs/tags/v$version" >/dev/null; then
    echo "v$version already exists." >&2
    exit 1
fi

echo "Releasing ${sha:0:9} as $version (last release: $last)."
git tag -a "v$version" -m "Floppy $version" "$sha"
git push --force-with-lease=stable origin "$sha:refs/heads/stable"
git push origin "refs/tags/v$version"
echo "Done. CI is building $version; then on the server: stable-update.sh (or wait for its cron run)."
