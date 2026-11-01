"""Background work for the API: CineTrack bootstrap jobs.

A job holds a large movies or shows batch that would take many 50-item
requests. Its state lives in the cache, not the database: a lost job answers
404 and the client resubmits, which is safe because every ensure is idempotent.
"""

import logging
import time

from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError

from api.cinetrack_bootstrap_views import (
    MAX_BOOTSTRAP_ITEMS,
    movie_results,
    show_results,
)
from app.services.sync_activity import batched_activity

logger = logging.getLogger(__name__)

BOOTSTRAP_JOB_TTL_SECONDS = 24 * 60 * 60
MAX_BOOTSTRAP_JOB_ITEMS = 2000
# A worker can wait longer than a request for SQLite's single writer.
JOB_LOCK_BACKOFF_SECONDS = (1, 3, 10, 30)


def bootstrap_job_key(user_id, job_id):
    """Cache key of one user's job; another user's id never finds it."""
    return f"cinetrack:bootstrap-job:{user_id}:{job_id}"


def _with_lock_retry(func):
    for attempt in range(len(JOB_LOCK_BACKOFF_SECONDS) + 1):
        try:
            return func()
        except OperationalError as error:
            if "locked" not in str(error).lower() or attempt == len(JOB_LOCK_BACKOFF_SECONDS):
                raise
            time.sleep(JOB_LOCK_BACKOFF_SECONDS[attempt])
    return None  # pragma: no cover


@shared_task(name="Run CineTrack bootstrap job", ignore_result=True)
def run_cinetrack_bootstrap_job(user_id, job_id):
    """Ensure a job's entries in 50-item chunks and store one result per entry."""
    key = bootstrap_job_key(user_id, job_id)
    job = cache.get(key)
    if not job or job["status"] != "queued":
        return
    user = get_user_model().objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        cache.delete(key)
        return

    results_for = movie_results if job["kind"] == "movies" else show_results
    entries = job.pop("entries")
    job.update(status="running", processed=0)
    cache.set(key, job, BOOTSTRAP_JOB_TTL_SECONDS)

    results = []
    for start in range(0, len(entries), MAX_BOOTSTRAP_ITEMS):
        chunk = entries[start : start + MAX_BOOTSTRAP_ITEMS]
        try:
            with batched_activity():
                results.extend(_with_lock_retry(lambda chunk=chunk: results_for(user, chunk)))
        except Exception:
            # Only this chunk is unknown. "error" tells the client to resubmit
            # these entries; the other chunks keep their exact outcomes.
            logger.exception("CineTrack bootstrap job %s chunk at %s failed", job_id, start)
            results.extend(
                {"source": entry["source"], "media_id": entry["media_id"], "status": "error"}
                for entry in chunk
            )
        job["processed"] = len(results)
        cache.set(key, job, BOOTSTRAP_JOB_TTL_SECONDS)

    job.update(status="done", results=results)
    cache.set(key, job, BOOTSTRAP_JOB_TTL_SECONDS)
