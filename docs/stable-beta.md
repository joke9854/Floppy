# Stable and beta servers

Two Floppy servers side by side:

| | Stable | Beta |
|---|---|---|
| Version | a release, e.g. `1.2.0` | the next patch's beta, e.g. `1.2.1-beta.3` |
| Code | a `vX.Y.Z` tag on a commit that went through beta | `CineTrack-API`: everything new |
| Image | `ghcr.io/joke9854/floppy:1.2.0` | `ghcr.io/joke9854/floppy:sha-<commit>` |
| Data | your real data | its own folder, filled with a **copy** of stable's data |
| Updates | when you release a version | automatically, after CI passes |
| Connected services | normal | paused (see below) |

`/api/v1/info/` reports the version, so you can always see what a server runs.
`1.2.1-beta.3` means "the third commit after 1.2.0, heading for 1.2.1".

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

Metadata (TMDB, TVDB, posters and similar) keeps working normally. Webhooks
from Plex, Jellyfin or Stremio keep going to stable only: don't point them at
beta.

## Layout on the server

```
~/floppy/                 stable (unchanged layout)
  docker-compose.yml        image: ghcr.io/joke9854/floppy:${FLOPPY_VERSION:-stable}
  .env                      FLOPPY_VERSION=1.2.0 (written by stable-update.sh)
  floppy.env                Floppy settings
  db/  backups/  db-backup-*/
~/floppy/beta/            beta (created by beta-setup.sh)
  docker-compose.yml        from deploy/stable-beta/docker-compose.beta.yml
  .env                      FLOPPY_BETA_TAG (written by beta-update.sh), BETA_PORT
  floppy.env                stable's settings with the beta address
  data/db  data/backups  data/redis
~/floppy/fork/            this repository; the scripts run from
                          ~/floppy/fork/deploy/stable-beta/
```

## Scripts

| Script | Where | What |
|---|---|---|
| `promote-stable.sh <commit> [patch\|minor\|major\|X.Y.Z]` | your PC | Releases a commit that is on `CineTrack-API` with green CI: tags `vX.Y.Z`, CI builds `:X.Y.Z` and `:stable`. Default is the next patch. |
| `stable-update.sh [X.Y.Z]` | server | Puts stable on the newest release (or the version given): backup while stopped, then start. Nothing happens if it already runs it. Going back = run it with the older version. |
| `beta-setup.sh <beta address>` | server, once | Creates `~/floppy/beta`. |
| `beta-refresh-data.sh` | server | Copies stable's data into beta (stable keeps running) and restarts beta. |
| `beta-update.sh` | server, cron | Moves beta to the newest `CineTrack-API` build with green CI. |

Database migrations only move forward: going back to an older version works
when it has the same migrations; otherwise restore a `db-backup-*` folder made
before the update.

## CineTrack

Beta has a different address, so CineTrack treats it as a separate Floppy and
never mixes the two. Keep your everyday phone on stable and point a test
install at beta.

## Postgres

`beta-refresh-data.sh` copies SQLite databases. On Postgres, copy with
`pg_dump` from stable into beta's own database instead, then start beta: its
start step pauses the schedules the same way.

### Moving a server from SQLite to Postgres

From v2 (P2-A) the container copies a SQLite install into Postgres by
itself. Add a Postgres service and the `DB_*` settings as in the repo's
`docker-compose.yml`, keep the `./db` volume, and start. The entrypoint:

- copies only when Postgres has no accounts and `db.sqlite3` has some;
- migrates the SQLite file first, then copies every table in one
  transaction and checks each table's row count;
- stops the container if anything fails, leaving Postgres empty, so Floppy
  never runs on an empty database in place of the real one;
- never changes or deletes `db.sqlite3` and writes
  `db.sqlite3.migrated-to-postgres` when done.

Try it on beta first. To go back, remove `DB_HOST`: Floppy uses the SQLite
file again, without anything written to Postgres since the copy.
