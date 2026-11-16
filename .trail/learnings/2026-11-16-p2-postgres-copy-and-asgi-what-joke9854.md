---
title: "P2 Postgres copy and ASGI: what bites"
author: Joke9854
date: 2026-11-16
branch: CineTrack-API
touches:
  - ".impeccable/critique/2026-11-03T18-33-51Z__floppy-bingehub-stream.md"
  - uv.lock
---

## Decided
- Postgres by default; an install with DB_HOST, Postgres without accounts and db.sqlite3 with accounts is copied at start (copy_sqlite_to_postgres): one transaction, COPY per table, values checked against Postgres columns, row counts compared, sequences reset, SQLite opened read-only and kept.
- The copy is decided from the two databases only; the db.sqlite3.migrated-to-postgres marker is a record. Skipping on the marker let an empty, recreated Postgres volume serve an empty library.
- The container serves config.asgi through gunicorn with config.asgi_worker.FloppyUvicornWorker (FLOPPY_ASGI=true from supervisord). Source installs keep config.wsgi on gthread.

## Tried and ruled out
- Leaving sync StreamingHttpResponse/FileResponse alone under ASGI: Django reads a sync iterator fully with sync_to_async(list) before sending. AsgiStreamingMiddleware pulls it one chunk at a time instead.
- Relying on gunicorn's post_request for the memory ceiling: the uvicorn worker never calls it. The check runs on the worker heartbeat (worker_should_retire).
- Reading "--needed" failing as "no copy needed": Postgres not up yet must be retried, or Floppy starts on an empty database.

## Watch out
- Under ASGI each request gets its own thread: config.asgi caps requests at GUNICORN_THREADS per worker, otherwise the Postgres pool (DB_POOL_MAX from the same number) runs out. SQLite CONN_MAX_AGE is 0 under ASGI.
- The local uv (0.12.13) refuses this repo (pinned 0.12.3); uv.lock edits were made by hand and checked by CI's uv sync --locked.
- No Postgres or Redis on the Windows dev machine: the copy test runs only in the CI sqlite-postgres-copy job. A test value that breaks a SQLite CHECK constraint (app_item.source) never reaches the copy.
- Postgres installs get no automatic snapshot: write_database_snapshot skips Postgres.
