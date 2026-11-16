"""Nightly snapshot of a Postgres database with pg_dump (v2 P2-A).

The SQLite snapshot copies the database file; a Postgres install had no
automatic backup at all. This writes a ``pg_dump --format=custom`` file to
the same ``BACKUP_DIR/database/`` folder, checks it with ``pg_restore
--list``, and keeps the newest ``max_keep``.

Restore into an empty database with
``pg_restore --no-owner --dbname=<db> <file>``.

The password goes to pg_dump through ``PGPASSWORD`` in its environment,
never on the command line, and is never logged.
"""

import logging
import os
import secrets
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger(__name__)

PREFIX = "floppy-postgres-"
SUFFIX = ".dump"
# Diagnostics from pg_dump are kept short in the log.
STDERR_LIMIT = 500


def _connection_env():
    database = settings.DATABASES["default"]
    env = dict(os.environ)
    env.update(
        {
            "PGHOST": str(database.get("HOST") or ""),
            "PGPORT": str(database.get("PORT") or ""),
            "PGUSER": str(database.get("USER") or ""),
            "PGDATABASE": str(database.get("NAME") or ""),
            "PGPASSWORD": str(database.get("PASSWORD") or ""),
        }
    )
    sslmode = (database.get("OPTIONS") or {}).get("sslmode")
    if sslmode:
        env["PGSSLMODE"] = str(sslmode)
    return {key: value for key, value in env.items() if value != ""}


def _prune(dest_dir, max_keep):
    snapshots = sorted(dest_dir.glob(f"{PREFIX}*{SUFFIX}"), reverse=True)
    for old in snapshots[max(1, max_keep) :]:
        try:
            old.unlink()
        except OSError:
            logger.warning("[db-snapshot] could not remove old snapshot %s", old.name)


def create_postgres_snapshot(dest_dir, *, max_keep, timeout_seconds=3600):
    """Write and verify one pg_dump snapshot; return its path or None."""
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        logger.error("[db-snapshot] pg_dump/pg_restore not installed; no snapshot")
        return None

    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    final = dest_dir / f"{PREFIX}{timestamp}-{secrets.token_hex(4)}{SUFFIX}"
    staging = dest_dir / f".{PREFIX}{secrets.token_hex(16)}{SUFFIX}.tmp"
    env = _connection_env()
    try:
        dump = subprocess.run(  # noqa: S603 - fixed binary and arguments
            [pg_dump, "--format=custom", "--no-owner", f"--file={staging}"],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if dump.returncode != 0:
            logger.error(
                "[db-snapshot] pg_dump failed (exit %s): %s",
                dump.returncode,
                dump.stderr.strip()[:STDERR_LIMIT],
            )
            return None
        listing = subprocess.run(  # noqa: S603 - fixed binary and arguments
            [pg_restore, "--list", str(staging)],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        if listing.returncode != 0 or "TABLE DATA" not in listing.stdout:
            logger.error("[db-snapshot] pg_dump output did not verify; discarded")
            return None
        staging.replace(final)
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.error(  # noqa: TRY400 - the error type only, no traceback
            "[db-snapshot] Postgres snapshot failed: %s", type(error).__name__
        )
        return None
    finally:
        if staging.exists():
            staging.unlink(missing_ok=True)

    _prune(dest_dir, max_keep)
    return final
