# Monitoring

Two pieces show errors and downtime without reading server logs:

- **Uptime Kuma** checks that Floppy answers. It needs no change to Floppy.
- **GlitchTip** (or any Sentry-compatible server) collects error reports with a
  stack trace. Floppy sends them only when `SENTRY_DSN` is set.

Both run beside Floppy as their own containers. Neither sends anything outside
your server unless you point it there.

## Before you start

Run these on the Floppy server. The examples use the server's LAN address;
find it with:

```bash
ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") print $(i+1)}'
```

Don't use the first address `hostname -I` prints: on a Docker host it is often a
bridge such as `172.x.0.1`, which only exists inside the server. If `ufw` is
active, open the ports:
`sudo ufw allow 3001/tcp` and `sudo ufw allow 8080/tcp`.

Below it is written `<server-ip>`. Floppy listens on port `8000`, Uptime Kuma
will use `3001` and GlitchTip `8080`. Pick other host ports if those are taken
(`docker ps` shows what is in use).

GlitchTip needs a Floppy image that includes error reporting (commit
`dca7c551` or later). Update Floppy first with `scripts/deploy_cinetrack.sh`.

## Uptime: Uptime Kuma

`GET /api/v1/health/` needs no token. It answers `200` with `"status": "ok"`
when the database, cache and Celery are reachable, and `500` with
`"status": "unavailable"` when one is not.

### Install

```bash
mkdir -p ~/uptime-kuma && cd ~/uptime-kuma
cat > compose.yml <<'YAML'
services:
  uptime-kuma:
    image: louislam/uptime-kuma:2
    restart: unless-stopped
    ports:
      - "3001:3001"
    volumes:
      - ./data:/app/data
YAML
docker compose up -d
```

Open `http://<server-ip>:3001`, choose the built-in SQLite database, and create
the admin account. Use the `:2` tag: version 1 no longer gets fixes.

### Add the Floppy monitor

**Add New Monitor**:

- Monitor Type: **HTTP(s)**
- Friendly Name: `Floppy`
- URL: `http://<server-ip>:8000/api/v1/health/`
- Heartbeat Interval: 60 seconds
- Accepted Status Codes: `200-299` (the default)

The status code is enough: a failing dependency answers `500` and a hung server
times out. Don't use a keyword monitor on `"status":"ok"`, because each entry
under `checks` carries that text too.

Under **Settings > Notifications**, add a channel (Telegram, ntfy, e-mail) and
turn it on for the monitor, so a failure reaches you.

## Errors: GlitchTip

GlitchTip gets its own directory, database and cache. Never point it at
Floppy's database.

### Install

```bash
mkdir -p ~/glitchtip && cd ~/glitchtip
curl -fsSL -o compose.yml https://glitchtip.com/assets/compose.sample.yml
openssl rand -hex 32    # copy the output for SECRET_KEY
nano compose.yml
```

In `compose.yml`, change:

- `SECRET_KEY`: the value `openssl` printed.
- `GLITCHTIP_DOMAIN`: `http://<server-ip>:8080`. The DSN GlitchTip hands out is
  built from this address, and Floppy's container must be able to reach it, so
  don't use `localhost`.
- `DEFAULT_FROM_EMAIL`: any address, for example `glitchtip@example.com`.
- `EMAIL_URL`: leave it as is, or set `consolemail://` if you have no SMTP
  server. Invitations and password resets then go to the container log.
- Under the `web` service's `ports`, change the host side to `8080`, because
  Floppy already uses `8000`. The container side must be the port GlitchTip
  listens on: check `docker compose logs web` for `Listening at:` after the
  first start. If it says `8080`, the line is `"8080:8080"`.

Then start it and create your login:

```bash
docker compose up -d
docker compose logs -f web    # wait until it says it is listening, then Ctrl+C
docker compose exec web ./manage.py createsuperuser
```

Open `http://<server-ip>:8080` and log in.

GlitchTip also has its own uptime checks (turned on in `compose.yml`). They
could replace Uptime Kuma, but this guide keeps the two apart.

### Connect Floppy

1. In GlitchTip, create an organization, then a project with platform
   **Django**.
2. Copy the project's DSN (**Settings > Projects > Floppy > DSN**). It looks
   like `http://<key>@<server-ip>:8080/1`.
3. Add it to the `environment` of the Floppy service in `~/floppy`'s compose file:

   ```yaml
   environment:
     - SENTRY_DSN=http://<key>@<server-ip>:8080/1
     - SENTRY_ENVIRONMENT=production
   ```

   If the service loads an `env_file`, add `SENTRY_DSN=...` and
   `SENTRY_ENVIRONMENT=production` there instead, without quotes.
   `SENTRY_DSN_FILE` reads the DSN from a Docker secret.
4. Restart Floppy: `cd ~/floppy && docker compose up -d --force-recreate`.

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

`docker ps` lists the Floppy container's name.

- Uptime Kuma: `docker stop <floppy-container>`; the monitor turns red
  within one interval. Start it again with `cd ~/floppy && docker compose up -d`.
- GlitchTip: run
  `docker exec <floppy-container> python manage.py shell -c "import sentry_sdk; sentry_sdk.capture_message('floppy monitoring test'); sentry_sdk.flush()"`
  and the message appears in the project.
