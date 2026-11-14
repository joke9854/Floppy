# Stable and beta servers

Two Floppy servers side by side:

| | Stable | Beta |
|---|---|---|
| Code | the `stable` branch: only commits promoted after testing | `CineTrack-API`: everything new |
| Image | `ghcr.io/joke9854/floppy:stable` | `ghcr.io/joke9854/floppy:sha-<commit>` (newest green build) |
| Data | your real data | its own folder, filled with a **copy** of stable's data |
| Updates | when you promote a commit | automatically, after CI passes |
| Connected services | normal | paused (see below) |

`/api/v1/info/` reports `stable-<commit>` or `beta-<commit>` as the version,
so you can always see what a server runs.

## What beta pauses

Beta runs with `FLOPPY_BETA_MODE=true`. On a copy of your data it would
otherwise push the same watched states to Jellyfin again, send duplicate
notifications, and refresh Trakt or Pocket Casts tokens, which logs your real
server out of them. So beta:

- pauses every per-user schedule (imports, pushes, polls) each time it starts,
  before anything else runs; it does not start if that step fails;
- skips every background task that contacts a connected service, even if
  something queues one;
- sends no notifications;
- shows "disabled on the beta server" for actions that contact a service right
  away (connect, push now, sign in to Trakt and similar);
- shows a thin "Beta server" banner on every page.

Metadata (TMDB, TVDB, posters and similar) keeps working normally.

Webhooks from Plex, Jellyfin or Stremio keep going to stable only: don't point
them at beta.

## One-time setup on the server

1. Put the stable server on the `stable` image. In your existing compose file,
   set `image: ghcr.io/joke9854/floppy:stable` for the Floppy service and remove
   any `build:` section. The first `:stable` image exists after the first
   promotion (see "Day to day").
2. Copy the `deploy/stable-beta/` folder to the server, for example
   `~/floppy/beta/`.
3. In that folder, create `beta.env` from `beta.env.example`: the same `SECRET`
   as stable, the beta address, the name of the stable container
   (`docker ps`). Then `chmod 600 beta.env`.
4. Add a public hostname for beta to the Cloudflare tunnel, pointing at
   `http://localhost:8001` (or the `BETA_PORT` you chose).
5. If the ghcr.io package is private, log Docker in once:
   `docker login ghcr.io` with a token that has `read:packages`.
6. Give beta its first copy of your data and start it:
   `./beta-refresh-data.sh`
7. Let beta follow CI: `crontab -e` and add
   `*/15 * * * * /home/<you>/floppy/beta/beta-update.sh >> /home/<you>/floppy/beta/beta-update.log 2>&1`
   (needs `jq`).

## Day to day

1. Work lands on `CineTrack-API` as usual. Within about 15 minutes of CI
   passing, beta runs it.
2. Try it on beta. Your data there is a copy: nothing you do reaches stable.
3. When it is good, promote that commit from your PC:
   `deploy/stable-beta/promote-stable.sh <commit>`
   It refuses commits that are not on `CineTrack-API` or whose CI is not green.
4. When the `:stable` image build is green, update stable on the server:
   `docker compose pull floppy && docker compose up -d floppy`

Fresh data on beta at any time: `./beta-refresh-data.sh`. Beta's previous
database is kept as `beta/db/db.sqlite3.previous`.

Going back: promote an older commit with
`ROLLBACK=1 deploy/stable-beta/promote-stable.sh <commit>`, then update stable.
Database migrations only move forward, so roll back only to a commit with the
same migrations, or restore stable's nightly snapshot from its `backups/`
folder.

## CineTrack

Beta has a different address, so CineTrack treats it as a separate Floppy
account: it never mixes the two. Keep your everyday phone on stable and point a
test install at beta.

## Postgres

`beta-refresh-data.sh` copies SQLite databases. On Postgres, copy with
`pg_dump` from stable into beta's own database instead, then start beta: the
beta start step pauses the schedules the same way.
