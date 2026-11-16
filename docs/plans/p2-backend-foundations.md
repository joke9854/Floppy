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
| P2-A | Postgres default and automatic SQLite copy | Built and tested in CI on a small fixture; nightly `pg_dump` snapshots for Postgres installs; installer and README stack use Postgres; beta trial ready (`beta-use-postgres.sh`), not yet run on real data |
| P2-B | Whole app on ASGI, server-sent events at `/api/v1/events/` | Built and pushed: the server switch (`db0d6b636`) and the events endpoint (`8a0938ea5`); beta checks pending |
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
  `docker-compose.sqlite.yml` for minimal installs (the old
  `docker-compose.postgres.yml` is gone).
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
    time and counts, and Floppy runs on Postgres from then on. The marker is
    a record only: if the Postgres volume is recreated empty, the next start
    copies again instead of serving an empty library.
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
- Found while planning (2026-11-16):
  - uvicorn 0.52.1 is already installed (through the MCP SDK); its
    `uvicorn.workers` is deprecated in favour of the `uvicorn-worker`
    package, which would be a new dependency.
  - The uvicorn worker honours `max_requests` and `timeout` but never calls
    gunicorn's `post_request`, so the per-worker memory ceiling in
    `config/gunicorn.py` (retire a worker above its RSS limit after 50
    requests and 60 s) has to move into a worker subclass that checks RSS
    on its heartbeat.
  - `preload_app` and the `gc.freeze()` in `when_ready` carry over.
  - Under ASGI each request runs its sync view in a thread of its own, so
    threads are no longer capped by `GUNICORN_THREADS`; the Postgres pool
    maximum needs its own setting.

### P2-C: poster size variants

- Cached images are stored in card sizes (for example 185 and 342 wide) with
  a content hash in the file name, served with `immutable` caching.
- Existing image URLs keep working unchanged; variants are an extra choice
  for the web and the API.

### P2-B commit 1: the server switch (2026-11-16)

- `supervisord.conf` runs `config.asgi:application` with `FLOPPY_ASGI=true`;
  `config/gunicorn.py` then picks `config.asgi_worker.FloppyUvicornWorker`.
  Source installs and `scripts/bench.sh` keep `config.wsgi` on gthread.
- `config/asgi.py` caps requests inside Django at `GUNICORN_THREADS` per
  worker (the rest wait, as for a free gthread thread), so the Postgres pool
  sized from the same number can't run out. `/api/v1/events` is not capped.
- The worker retires itself above the memory ceiling on its heartbeat (the
  same rule as the gthread `post_request` hook, `worker_should_retire`) and
  waits at most `graceful_timeout` for requests in flight on shutdown.
- SQLite connections close after each request under ASGI
  (`CONN_MAX_AGE` 0); Celery keeps persistent ones.
- `app.asgi_streaming.AsgiStreamingMiddleware`: Django reads a sync
  streaming body into memory in full under ASGI; the middleware streams it
  chunk by chunk instead (exports, list CSV, backups, FileResponse).
- uvicorn is now a declared dependency at the locked 0.52.1 (the lock was
  edited by hand: the local uv is not the pinned 0.12.3; CI's
  `uv sync --locked` checks it).
- Measured locally under uvicorn on SQLite: 110 API and health requests at
  8 concurrent, threads stayed at 8-9, no SQLite handles left open; the
  Letterboxd export streamed chunked with no buffering warning.
- Not checkable here (gunicorn does not run on Windows): the gunicorn
  worker itself, which the Docker Image workflow's smoke run starts. Check
  on beta: CineTrack sync, image URLs (scheme and host behind the tunnel)
  and memory per worker on the minimal tier.

### P2-B commit 2: `/api/v1/events/`

- `GET /api/v1/events/` streams the user's events as server-sent events:
  `retry`, then `event: <type>` / `data: <json>`, a `: ping` comment every
  20 s (under nginx's 60 s read timeout), and the stream ends after 30
  minutes so workers recycle and revoked tokens stop; EventSource
  reconnects.
- Scope `events:read` (new, opt-in): events cover tasks from every app of
  the user, so a narrow token does not see them. Session logins get them
  once the P3 session bridge exists; until then only tokens reach it.
- First event: `task.finished` (`task_id`, `state`) from Celery's
  `task_postrun` for tasks with a `user_id`; eager runs are skipped.
  Events are ids and states only, published over Redis pub/sub
  (`app/live_events.py`), never stored.
- The stream gives back the request's database connection before it
  starts, sends `X-Accel-Buffering: no`, is not counted against the request
  cap, and answers 503 under WSGI (source installs), where it would hold a
  thread.
- Contract: `openapi-full.yaml` gains the operation; `openapi.yaml` is
  unchanged. Check on beta through the real tunnel that events arrive
  promptly and the connection survives idle minutes.
