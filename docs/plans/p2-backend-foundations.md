# P2: backend foundations

Part of `floppy-v2.md`. Started 2026-11-16.

## What already exists

- **Postgres:** supported when `DB_HOST` is set (`config/settings.py`, psycopg 3
  with a connection pool, `docker-compose.postgres.yml`). SQLite is the
  default and both servers (stable and beta) run on it.
- **Priority job queues:** done before v2. Redis priority ordering
  (`queue_order_strategy: priority`, steps 0-9), task priorities in
  `CELERY_TASK_ROUTES`, separate `interactive` and `discover` workers, and
  `celery_queue_plan` folds them together on small hosts. Nothing to build.
- **Images:** cached posters are files served by nginx (X-Accel-Redirect);
  fanart.tv art is shrunk on download; the web asks TMDB for `w185`/`w342`
  through `tmdb_srcset`. No stored size variants, no content-hashed names.
- **Web process:** gunicorn `gthread` on `config.wsgi`. No ASGI, no events.

## Decisions (user, 2026-11-16)

- **Postgres default with automatic migration.** New installs get Postgres
  in the compose file. An existing install that starts with `DB_HOST` set,
  an empty Postgres database and a `db.sqlite3` is copied over automatically
  at start.
- **Whole app on ASGI.** gunicorn with uvicorn workers serves all of Django,
  not a side process for events only.

## Slices

| Slice | Content | Status |
|---|---|---|
| P2-A | Postgres default and automatic SQLite copy | Not started |
| P2-B | Whole app on ASGI, server-sent events at `/api/v1/events/` | Not started |
| P2-C | Poster size variants with content-hashed names | Not started |

Order: A before B, because ASGI needs a connection pool. Under ASGI every
request runs in its own thread, so persistent connections
(`CONN_MAX_AGE`) must be off. Django pools Postgres connections but not SQLite
ones, so SQLite installs on ASGI reconnect on every request (connect, PRAGMAs,
cold page cache). Postgres first means the common path keeps pooling; the
SQLite cost is measured on the minimal tier in P2-B.

### P2-A: Postgres default and automatic copy

- **Compose:** `docker-compose.yml` gains a `db` service (postgres:16-alpine)
  and `DB_*` settings; the SQLite-only file stays as
  `docker-compose.sqlite.yml` for minimal installs.
- **Copy at start** (`manage.py migrate_sqlite_to_postgres`, called by the
  entrypoint before `migrate` when the conditions hold):
  - runs only when `DB_HOST` is set, the SQLite file exists and has
    `django_migrations`, and the Postgres database has no Floppy tables;
  - brings the SQLite file to the latest migration first, then creates the
    schema on Postgres with `migrate`, so both sides have the same tables;
  - copies every table with COPY in one transaction, with foreign key checks
    deferred, converting values through the model fields (booleans,
    timestamps as UTC, JSON, UUIDs, binary);
  - checks the row count of every table, resets the sequences, and commits
    only if every count matches. Any failure rolls back: Postgres stays
    empty and the next start tries again;
  - leaves the SQLite file in place: only the pending migrations a normal
    start would run touch it, and nothing deletes it. After a successful copy it
    writes a marker next to it (`db.sqlite3.migrated-to-postgres`) with the
    time and counts, and Floppy runs on Postgres from then on.
- **Beta first:** `beta-refresh-data.sh` keeps copying SQLite; switching
  beta to Postgres is the real test, then stable on a release.
- **Tests:** the copy runs in CI against a Postgres service container
  (there is no Postgres on the dev machine), with a fixture covering every
  field type the models use.

### P2-B: ASGI and server-sent events

- gunicorn keeps the process management and memory recycling; the worker
  class becomes `uvicorn_worker.UvicornWorker` on `config.asgi`.
- `CONN_MAX_AGE` 0 under ASGI; the Postgres pool size follows the worker's
  thread limit instead of gunicorn threads.
- `GET /api/v1/events/` streams events for the signed-in user, fed by Redis
  pub/sub (works on SQLite installs too). First events: task finished,
  import progress, library changed. nginx turns off buffering for the path.
- Checked with uvicorn on the dev machine, then the Docker Image workflow
  and beta (gunicorn does not run on Windows).

### P2-C: poster size variants

- Cached images are stored in card sizes (for example 185 and 342 wide) with
  a content hash in the file name, served with `immutable` caching.
- Existing image URLs keep working unchanged; variants are an extra choice
  for the web and the API.
