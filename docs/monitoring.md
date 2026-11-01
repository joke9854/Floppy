# Monitoring

Two pieces show errors and downtime without reading server logs:

- **Uptime Kuma** checks that Floppy answers. It needs no change to Floppy.
- **GlitchTip** (or any Sentry-compatible server) collects error reports with a
  stack trace. Floppy sends them only when `SENTRY_DSN` is set.

Both run beside Floppy as their own containers. Neither sends anything outside
your server unless you point it there.

## Uptime: Uptime Kuma

`GET /api/v1/health/` needs no token. It answers `200` with `"status": "ok"`
when the database, cache and Celery are reachable, and `500` with
`"status": "unavailable"` when one is not.

```yaml
services:
  uptime-kuma:
    image: louislam/uptime-kuma:1
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - ./uptime-kuma:/app/data
```

In Uptime Kuma, add a monitor:

- Type: **HTTP(s)**
- URL: `http://<floppy-host>:8000/api/v1/health/`
- Accepted status codes: `200-299` (the default)
- Interval: 60 seconds

The status code is enough: a failing dependency answers `500` and a hung server
times out. Don't use a keyword monitor on `"status":"ok"`, because each entry
under `checks` carries that text too. Add a notification
(Telegram, ntfy, e-mail) so a failure reaches you.

## Errors: GlitchTip

Install GlitchTip with its own guide (<https://glitchtip.com/documentation/install>).
It needs Postgres and Redis of its own; do not share Floppy's database. Then:

1. In GlitchTip, create an organization and a **Django** project.
2. Copy the project's DSN.
3. Give it to Floppy and restart it:

   ```yaml
   environment:
     - SENTRY_DSN=https://<key>@glitchtip.example/1
     - SENTRY_ENVIRONMENT=production
   ```

   `SENTRY_DSN_FILE` reads the DSN from a Docker secret instead.

Floppy reports unhandled errors from web requests and Celery tasks. Events are
tagged with the running version, so a report names the commit that produced it.
Performance tracing is off.

### What a report contains

`src/config/error_reporting.py` scrubs every event before it leaves Floppy:

- The request keeps only its method and its URL without query string or
  user-info. Headers, cookies, bodies and client addresses are dropped.
- Stack frames keep file, function and line, but no local variables and no
  source lines.
- Messages, exception values and breadcrumbs go through the same redaction as
  the logs ([log-redaction.md](architecture/log-redaction.md)).

An API key, an `Authorization` header or a request body never reaches
GlitchTip.

## Checking it works

- Uptime Kuma: stop the Floppy container; the monitor turns red within one
  interval.
- GlitchTip: run
  `docker exec <floppy-container> python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('floppy monitoring test'); sentry_sdk.flush()"`
  and the message appears in the project.
