ARG PYTHON_VERSION=3.12
ARG ALPINE_VERSION=3.24

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS repo_meta

WORKDIR /repo
COPY . .
RUN python - <<'PY'
from pathlib import Path
from urllib.parse import urlparse

config_path = Path(".git/config")
owner = ""

if config_path.exists():
    origin_url = None
    in_origin = False
    for raw_line in config_path.read_text().splitlines():
        line = raw_line.strip()
        if line.startswith('[remote "origin"]'):
            in_origin = True
            continue
        if line.startswith("[") and in_origin:
            in_origin = False
        if in_origin and line.startswith("url"):
            _, value = line.split("=", 1)
            origin_url = value.strip()
            break

    if origin_url:
        value = origin_url.strip()
        if value.startswith("git@") and ":" in value:
            value = value.split(":", 1)[1]
        parsed = urlparse(value)
        repo_path = parsed.path if parsed.netloc else value
        repo_path = repo_path.strip("/")
        if repo_path.endswith(".git"):
            repo_path = repo_path[:-4]
        if repo_path:
            owner = repo_path.split("/", 1)[0]

Path("/repo_owner").write_text(owner)
PY

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /floppy

COPY ./pyproject.toml ./uv.lock ./
COPY ./mcp_server/pyproject.toml ./mcp_server/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-install-workspace

COPY ./mcp_server ./mcp_server
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-default-groups --no-editable

# v2 P3: the SvelteKit app (web/). Built with Alpine's own Node, the same
# one the runtime image installs. The adapter-node output is self-contained
# (no node_modules at runtime); package.json only says it is ES modules.
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS web_builder

RUN apk add --no-cache nodejs npm
WORKDIR /web
COPY ./web/package.json ./web/package-lock.json ./web/.npmrc ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund
COPY ./web ./
RUN npm run build

FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION}

# https://stackoverflow.com/questions/58701233/docker-logs-erroneously-appears-empty-until-container-stops
ENV PYTHONUNBUFFERED=1
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Define build argument with default value
ARG VERSION=dev
ARG COMMIT_SHA=unknown
# Set it as an environment variable
ENV VERSION=$VERSION
ENV COMMIT_SHA=$COMMIT_SHA
# A stray environment override (an orchestrator's persisted .env, a leftover
# manual "docker run -e", etc.) can otherwise shadow the ENV above and make
# the running container silently misreport its own build identity, with
# nothing in this image able to tell the difference. Recording the same
# values in a plain file baked into the image gives entrypoint.sh something
# runtime environment variables cannot override, to restore VERSION and
# COMMIT_SHA from before it reports either one.
RUN printf 'VERSION=%s\nCOMMIT_SHA=%s\n' "$VERSION" "$COMMIT_SHA" > /etc/floppy-build-info

# supervisord expands %(ENV_...)s in supervisord.conf and refuses to start if a
# referenced variable is unset, so these need image-level defaults even though
# entrypoint.sh overwrites them from the detected resource tier (issue #521).
ENV FLOPPY_CELERY_ROLE=background
ENV FLOPPY_CELERY_QUEUES=celery
ENV FLOPPY_START_INTERACTIVE_WORKER=true
ENV FLOPPY_START_DISCOVER_WORKER=true

COPY ./runtime-entrypoint.sh /runtime-entrypoint.sh
COPY ./entrypoint.sh /entrypoint.sh
COPY ./supervisord.conf /etc/supervisord.conf
# Keep one checked-in listener marker. runtime-entrypoint.sh validates the
# configured port and renders the IPv4/IPv6 runtime configs from this template.
COPY ./nginx.conf /etc/nginx/nginx.conf.template

WORKDIR /floppy

# Legacy compat: pre-rename compose files bind-mount ./db to /yamtrack/db.
# Without this symlink such a mount lands on a stale path and the app
# silently creates an empty database.
RUN ln -s /floppy /yamtrack

# postgresql-client: pg_dump/pg_restore for the nightly Postgres snapshot
# (config/postgres_snapshot.py). A newer pg_dump reads older servers.
# nodejs: the SvelteKit server (v2 P3, supervisord program web).
RUN apk add --no-cache nginx shadow postgresql-client nodejs \
    && pg_dump --version \
    && node --version \
    && chmod +x /runtime-entrypoint.sh /entrypoint.sh \
    # create user abc for later PUID/PGID mapping
    && useradd -U -M -s /bin/sh abc \
    # Create required nginx directories and set permissions
    && mkdir -p /var/log/nginx \
    && mkdir -p /var/lib/nginx/body

COPY --from=repo_meta /repo_owner /etc/floppy/fork_owner
COPY --from=builder /opt/venv /opt/venv
COPY --from=web_builder /web/build /floppy/web/build
COPY --from=web_builder /web/package.json /floppy/web/package.json
RUN ln -s /opt/venv /floppy/.venv

# Django app
COPY src ./
RUN SECRET=build-time-placeholder python manage.py collectstatic --noinput

# MCP server (mcp/floppy_mcp) — bundled so `docker exec` always runs the
# version shipped with this image, instead of a user's local checkout that
# can silently drift from the app version.
COPY mcp_server ./mcp_server

# 8000 remains the documented/default port. FLOPPY_PORT can select a different
# runtime listener; EXPOSE is image metadata and cannot express a dynamic port.
EXPOSE 8000

CMD ["/runtime-entrypoint.sh"]

HEALTHCHECK --interval=45s --timeout=15s --start-period=30s --retries=5 \
  CMD port="$(cat /run/floppy/server-port 2>/dev/null)" \
      && case "$port" in *[!0-9]*|'') exit 1 ;; esac \
      && wget --no-verbose --tries=1 --spider "http://127.0.0.1:${port}/health/" \
      || exit 1
