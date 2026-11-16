"""Periodic raw SQLite snapshot for disaster recovery (#1053).

CSV export (integrations.exports.write_backup) cannot replace a physically
damaged db.sqlite3: it needs a working Django install to import into, and it
carries only media/ratings/lists, not accounts or integration credentials.
This task writes a verified, atomically-published copy of the live database
itself, so a corrupted file has something real to be replaced with.
"""

import logging
import time
from contextlib import suppress
from pathlib import Path

from celery import shared_task
from django.conf import settings

from app.memory_envelope import sample_memory
from config.sqlite_integrity import create_live_database_snapshot

logger = logging.getLogger(__name__)


@shared_task(name="Write database snapshot", ignore_result=True)
def write_database_snapshot():
    """Write a verified snapshot to BACKUP_DIR/database/.

    SQLite: a raw .sqlite3 copy. Postgres: a pg_dump custom-format file
    (config/postgres_snapshot.py). No-ops when the feature is disabled -- checked here, not only at schedule-definition time, so
    toggling DB_SNAPSHOT_ENABLED takes effect on the next run. Never raises:
    a snapshot failure must never crash a worker or retry-storm.
    """
    if not settings.DB_SNAPSHOT_ENABLED:
        return {"status": "skipped", "reason": "disabled"}
    if not settings.USING_SQLITE_DATABASE:
        return _write_postgres_snapshot()

    # Both cgroup envelopes, bracketing the copy. Production's largest
    # observed excursion -- roughly 1-2 GB to above 5 GB, decaying over hours
    # -- coincides with this task, and the shape (a couple of GB of write I/O,
    # no comparable process growth) points at filesystem page cache rather
    # than at anything Python allocated. This records that rather than
    # inferring it: the copy is written and then read back in full by
    # PRAGMA quick_check, so a snapshot charges the cgroup roughly twice its
    # own size in `file` unless the cache is released afterwards.
    before = sample_memory()
    started = time.perf_counter()
    try:
        dest_dir = Path(settings.BACKUP_DIR) / "database"
        path = create_live_database_snapshot(
            str(settings.FLOPPY_DB_PATH),
            dest_dir,
            max_keep=settings.DB_SNAPSHOT_RETENTION_COUNT,
            timeout_seconds=settings.SQLITE_BUSY_TIMEOUT_SECONDS,
        )
    except Exception:
        logger.exception("Database snapshot task failed unexpectedly")
        return {"status": "error", "reason": "unexpected failure"}

    if path is None:
        return {"status": "error", "reason": "snapshot could not be verified"}

    _log_snapshot_envelope(path, before, (time.perf_counter() - started) * 1000)
    return {"status": "ok", "path": str(path)}


def _write_postgres_snapshot():
    """Postgres branch of write_database_snapshot; never raises."""
    from config.postgres_snapshot import create_postgres_snapshot

    try:
        path = create_postgres_snapshot(
            Path(settings.BACKUP_DIR) / "database",
            max_keep=settings.DB_SNAPSHOT_RETENTION_COUNT,
        )
    except Exception:
        logger.exception("Postgres snapshot task failed unexpectedly")
        return {"status": "error", "reason": "unexpected failure"}
    if path is None:
        return {"status": "error", "reason": "pg_dump snapshot failed"}
    logger.info("db_snapshot name=%s engine=postgres", path.name)
    return {"status": "ok", "path": str(path)}


def _format(value) -> str:
    """Render a possibly-unknown measurement, never as a misleading zero."""
    return "unknown" if value is None else str(value)


def _log_snapshot_envelope(path: Path, before, duration_ms: float) -> None:
    """Emit one structured line tying the snapshot to the cgroup it moved.

    Only the file name is logged, not the full path: BACKUP_DIR is operator
    configuration and the name alone is enough to match this line against the
    page_cache_release line the writer emits for the same snapshot.
    """
    size_bytes = None
    with suppress(OSError):
        size_bytes = path.stat().st_size
    after = sample_memory()
    logger.info(
        "db_snapshot name=%s bytes=%s duration_ms=%.0f "
        "cgroup_before=%s cgroup_after=%s anon_before=%s anon_after=%s "
        "file_before=%s file_after=%s",
        path.name,
        _format(size_bytes),
        duration_ms,
        _format(before.cgroup_current_bytes),
        _format(after.cgroup_current_bytes),
        _format(before.cgroup_anon_bytes),
        _format(after.cgroup_anon_bytes),
        _format(before.cgroup_file_bytes),
        _format(after.cgroup_file_bytes),
    )
