"""Request-free connect/disconnect/settings/import actions for integrations.

The web views in ``integrations.views`` and the API call these functions. They
take the acting ``user`` plus plain values, never a ``request``.

Errors are raised as ``IntegrationError``. ``message`` is user-safe text (it
never carries remote exception text, URLs, keys or tokens). ``web_message`` is
the exact string the web UI has always shown, which may include the remote
error text; API callers must not echo it.
"""

# ruff: noqa: TRY003, EM101, EM102
# IntegrationError carries user-safe messages by design; they are passed inline.

import json
import logging
import re
import time
import zoneinfo
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import croniter
import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

import users
from app.db_retry import run_retryable_db_operation
from app.log_safety import exception_summary
from app.providers import services
from integrations import (
    gpodder_api,
    koito_api,
    lastfm_api,
    pocketcasts_api,
    psn_api,
    tasks,
    xbox_api,
)
from integrations.gpodder_api import GPodderAuthError, GPodderClientError
from integrations.imports import helpers, stremio
from integrations.imports.audiobookshelf import (
    AudiobookshelfAuthError,
    AudiobookshelfClient,
)
from integrations.imports.koreader import (
    KoreaderAuthError,
    KoreaderClient,
    KoreaderClientError,
)
from integrations.imports.radarr import RadarrClient
from integrations.imports.sonarr import SonarrClient
from integrations.jellyfin_client import (
    JellyfinAuthError,
    JellyfinClient,
    JellyfinClientError,
)
from integrations.jellyfin_sync import (
    JELLYFIN_PUSH_INTERVAL_MINUTES,
    JELLYFIN_PUSH_TASK_NAME,
)
from integrations.lastfm_api import (
    LastFMAPIError,
    LastFMClientError,
    LastFMRateLimitError,
)
from integrations.models import (
    AudiobookshelfAccount,
    CollectionSourceState,
    GPodderAccount,
    JellyfinAccount,
    KoitoAccount,
    KoreaderAccount,
    KoreaderDocumentLink,
    LastFMAccount,
    PlexAccount,
    PlexWebhookShare,
    PocketCastsAccount,
    PSNAccount,
    RadarrInstance,
    SonarrInstance,
    StorytellerAccount,
    StremioAccount,
    XboxAccount,
)
from integrations.plex_watchlist import (
    WATCHLIST_SYNC_INTERVAL_MINUTES,
    WATCHLIST_TASK_NAME,
)
from integrations.pocketcasts_api import PocketCastsAuthError
from integrations.task_filters import user_kwargs_regex

logger = logging.getLogger(__name__)

ARR_SYNC_INTERVAL_HOURS = 2
RADARR_RECURRING_TASK_NAME = "Import from Radarr (Recurring)"
SONARR_RECURRING_TASK_NAME = "Import from Sonarr (Recurring)"
GPODDER_RECURRING_TASK_NAME = "Import from GPodder (Recurring)"
STORYTELLER_RECURRING_TASK_NAME = "Import from Storyteller (Recurring)"
STREMIO_RECURRING_TASK_NAME = "Import from Stremio (Recurring)"
XBOX_RECURRING_TASK_NAME = "Import from Xbox (Recurring)"
PSN_RECURRING_TASK_NAME = "Import from PSN (Recurring)"
POCKETCASTS_RECURRING_TASK_NAME = "Import from Pocket Casts (Recurring)"
AUDIOBOOKSHELF_RECURRING_TASK_NAME = "Import from Audiobookshelf (Recurring)"
KOREADER_IMPORT_TASK_NAME = "Import from KOReader"
KOREADER_MAX_COMPLETION = 100
CONSOLE_RECURRING_FREQUENCIES = {"daily": "*", "2days": "*/2"}
CONSOLE_DEFAULT_IMPORT_TIME = "04:00"
HTTP_SERVER_ERROR = 500


class IntegrationError(Exception):
    """A connect/disconnect/settings/import action could not be completed.

    ``message`` is user-safe. ``unreachable`` is True when the remote service
    could not be reached (network failure, timeout, remote 5xx) and False for
    bad credentials, invalid input or a failed precondition.
    ``web_message`` is the exact text the web UI shows; it may include remote
    error text and must not be returned from the API.
    """

    def __init__(self, message, *, unreachable=False, web_message=None):
        """Store the safe message, the reachability flag and the web text."""
        super().__init__(message)
        self.message = message
        self.unreachable = unreachable
        self.web_message = web_message or message


class NotConnectedError(IntegrationError):
    """The action needs a connected account (or instance) that is missing."""


class AlreadyRunningError(IntegrationError):
    """The requested import is already running."""


@dataclass(frozen=True)
class ImportQueued:
    """Outcome of an import start whose follow-up message depends on scheduling.

    ``outcome`` is "queued" for a one-off run, "scheduled" when a recurring
    schedule was created and "reenabled" when a disabled one was revived.
    ``schedule_created`` is True when a new recurring schedule was set up
    alongside the queued run (Pocket Casts, GPodder).
    """

    result: Any = None
    outcome: str = "queued"
    schedule_created: bool = False


def _chain_has(exc, types):
    """Return whether ``exc`` or anything in its cause/context chain is one of ``types``."""
    seen = 0
    current = exc
    while current is not None and seen < 10:  # noqa: PLR2004
        if isinstance(current, types):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


def _arr_unreachable(exc):
    return _chain_has(exc, requests.RequestException)


def _jellyfin_unreachable(exc):
    """Classify a Jellyfin client error as unreachable (network/5xx) or not."""
    if isinstance(exc, JellyfinAuthError):
        return False
    if isinstance(exc.__cause__, requests.RequestException):
        return True
    match = re.search(r"request failed \((\d{3})\)", str(exc))
    if match:
        return int(match.group(1)) >= HTTP_SERVER_ERROR
    return True


def _console_unreachable(exc):
    return _chain_has(exc, (requests.RequestException, services.ProviderAPIError))


def _run_with_lock_retry(operation_name, fn):
    """Run an integration connect/disconnect DB write with retry on SQLite locks.

    Connect/disconnect actions create or delete `django_celery_beat`
    `PeriodicTask` rows, which fire a signal that writes to a shared
    singleton row (`PeriodicTasks.changed()`) — a serialization hotspot on
    SQLite. Wrapping the write in a retried transaction turns a transient
    lock into a short delay instead of a 503 (see issue #1112).

    `max_retries=1` (2 attempts total) rather than the helper's default of
    5: each attempt can block for up to `SQLITE_BUSY_TIMEOUT_SECONDS`
    (30s by default) before raising, and nginx.conf sets no explicit
    `proxy_read_timeout` (nginx's own default is 60s) — more attempts would
    risk the proxy returning a gateway timeout to the user while this view
    keeps retrying underneath it, so the write could still commit after the
    client has already seen a failure.
    """

    def _atomic_fn():
        with transaction.atomic():
            return fn()

    return run_retryable_db_operation(
        _atomic_fn, operation_name=operation_name, max_retries=1
    ).value


def _plex_watchlist_task_filter(user_id):
    """Match a user's watchlist task regardless of JSON spacing/quotes."""
    return (
        Q(kwargs__contains=f"'user_id': {user_id},")
        | Q(
            kwargs__contains=f"'user_id': {user_id}" + "}",
        )
        | Q(
            kwargs__contains=f'"user_id": {user_id},',
        )
        | Q(
            kwargs__contains=f'"user_id": {user_id}' + "}",
        )
    )


def _periodic_task_filter_for_user(user_id):
    """Match a user's periodic task regardless of JSON spacing/quotes."""
    return _plex_watchlist_task_filter(user_id)


def _periodic_task_filter_for_instance(instance_id):
    """Match a Radarr/Sonarr instance's periodic task regardless of JSON spacing/quotes."""
    return (
        Q(kwargs__contains=f"'instance_id': {instance_id},")
        | Q(kwargs__contains=f"'instance_id': {instance_id}" + "}")
        | Q(kwargs__contains=f'"instance_id": {instance_id},')
        | Q(kwargs__contains=f'"instance_id": {instance_id}' + "}")
    )


def _next_arr_sync_start(now=None):
    """Return the next future ARR sync boundary."""
    current = (now or timezone.now()).astimezone(timezone.get_default_timezone())
    boundary = current.replace(minute=0, second=0, microsecond=0)
    hours_until_next = ARR_SYNC_INTERVAL_HOURS - (
        boundary.hour % ARR_SYNC_INTERVAL_HOURS
    )
    return boundary + timedelta(hours=hours_until_next)


def _ensure_plex_watchlist_schedule(user, plex_account):
    """Create or enable the per-user Plex watchlist interval schedule."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    next_interval_start = timezone.now() + timedelta(
        minutes=WATCHLIST_SYNC_INTERVAL_MINUTES
    )
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=WATCHLIST_SYNC_INTERVAL_MINUTES,
        period=IntervalSchedule.MINUTES,
    )
    task_filter = PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=WATCHLIST_TASK_NAME,
    )
    existing_task = task_filter.first()
    if existing_task:
        was_enabled = existing_task.enabled
        updated_fields = []
        desired_name = (
            f"{WATCHLIST_TASK_NAME} for "
            f"{plex_account.plex_username or user.username} "
            f"(every {WATCHLIST_SYNC_INTERVAL_MINUTES} minutes)"
        )
        desired_kwargs = json.dumps({"user_id": user.id, "mode": "watchlist"})
        if existing_task.name != desired_name:
            existing_task.name = desired_name
            updated_fields.append("name")
        if existing_task.interval_id != interval.id:
            existing_task.interval = interval
            updated_fields.append("interval")
        if existing_task.crontab_id is not None:
            existing_task.crontab = None
            updated_fields.append("crontab")
        if existing_task.clocked_id is not None:
            existing_task.clocked = None
            updated_fields.append("clocked")
        if existing_task.solar_id is not None:
            existing_task.solar = None
            updated_fields.append("solar")
        if existing_task.one_off:
            existing_task.one_off = False
            updated_fields.append("one_off")
        if existing_task.kwargs != desired_kwargs:
            existing_task.kwargs = desired_kwargs
            updated_fields.append("kwargs")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if existing_task.start_time is None or not was_enabled:
            existing_task.start_time = next_interval_start
            updated_fields.append("start_time")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task

    return PeriodicTask.objects.create(
        name=(
            f"{WATCHLIST_TASK_NAME} for "
            f"{plex_account.plex_username or user.username} "
            f"(every {WATCHLIST_SYNC_INTERVAL_MINUTES} minutes)"
        ),
        task=WATCHLIST_TASK_NAME,
        interval=interval,
        kwargs=json.dumps({"user_id": user.id, "mode": "watchlist"}),
        start_time=next_interval_start,
        enabled=True,
    )


def _disable_plex_watchlist_schedule(user):
    """Delete any per-user Plex watchlist periodic tasks."""
    from django_celery_beat.models import PeriodicTask

    return PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=WATCHLIST_TASK_NAME,
    ).delete()


def _ensure_jellyfin_push_schedule(user, jellyfin_account):
    """Create or enable the per-user Jellyfin watched-state push schedule."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    next_interval_start = timezone.now() + timedelta(
        minutes=JELLYFIN_PUSH_INTERVAL_MINUTES
    )
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=JELLYFIN_PUSH_INTERVAL_MINUTES,
        period=IntervalSchedule.MINUTES,
    )
    task_filter = PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=JELLYFIN_PUSH_TASK_NAME,
    )
    existing_task = task_filter.first()
    if existing_task:
        was_enabled = existing_task.enabled
        updated_fields = []
        desired_name = (
            f"{JELLYFIN_PUSH_TASK_NAME} for "
            f"{jellyfin_account.jellyfin_username or user.username} "
            f"(every {JELLYFIN_PUSH_INTERVAL_MINUTES} minutes)"
        )
        desired_kwargs = json.dumps({"user_id": user.id})
        if existing_task.name != desired_name:
            existing_task.name = desired_name
            updated_fields.append("name")
        if existing_task.interval_id != interval.id:
            existing_task.interval = interval
            updated_fields.append("interval")
        if existing_task.crontab_id is not None:
            existing_task.crontab = None
            updated_fields.append("crontab")
        if existing_task.kwargs != desired_kwargs:
            existing_task.kwargs = desired_kwargs
            updated_fields.append("kwargs")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if existing_task.start_time is None or not was_enabled:
            existing_task.start_time = next_interval_start
            updated_fields.append("start_time")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task

    return PeriodicTask.objects.create(
        name=(
            f"{JELLYFIN_PUSH_TASK_NAME} for "
            f"{jellyfin_account.jellyfin_username or user.username} "
            f"(every {JELLYFIN_PUSH_INTERVAL_MINUTES} minutes)"
        ),
        task=JELLYFIN_PUSH_TASK_NAME,
        interval=interval,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=next_interval_start,
        enabled=True,
    )


def _disable_jellyfin_push_schedule(user):
    """Delete any per-user Jellyfin push periodic tasks."""
    from django_celery_beat.models import PeriodicTask

    return PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=JELLYFIN_PUSH_TASK_NAME,
    ).delete()


def _ensure_jellyfin_pull_schedule(user, jellyfin_account):
    """Create or enable the per-user Jellyfin history pull schedule."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    pull_task_name = tasks.JELLYFIN_PULL_TASK_NAME
    pull_interval_minutes = tasks.JELLYFIN_PULL_INTERVAL_MINUTES

    next_interval_start = timezone.now() + timedelta(minutes=pull_interval_minutes)
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=pull_interval_minutes,
        period=IntervalSchedule.MINUTES,
    )
    task_filter = PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=pull_task_name,
    )
    existing_task = task_filter.first()
    if existing_task:
        was_enabled = existing_task.enabled
        updated_fields = []
        desired_name = (
            f"{pull_task_name} for "
            f"{jellyfin_account.jellyfin_username or user.username} "
            f"(every {pull_interval_minutes} minutes)"
        )
        desired_kwargs = json.dumps({"user_id": user.id})
        if existing_task.name != desired_name:
            existing_task.name = desired_name
            updated_fields.append("name")
        if existing_task.interval_id != interval.id:
            existing_task.interval = interval
            updated_fields.append("interval")
        if existing_task.crontab_id is not None:
            existing_task.crontab = None
            updated_fields.append("crontab")
        if existing_task.kwargs != desired_kwargs:
            existing_task.kwargs = desired_kwargs
            updated_fields.append("kwargs")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if existing_task.start_time is None or not was_enabled:
            existing_task.start_time = next_interval_start
            updated_fields.append("start_time")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task

    return PeriodicTask.objects.create(
        name=(
            f"{pull_task_name} for "
            f"{jellyfin_account.jellyfin_username or user.username} "
            f"(every {pull_interval_minutes} minutes)"
        ),
        task=pull_task_name,
        interval=interval,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=next_interval_start,
        enabled=True,
    )


def _disable_jellyfin_pull_schedule(user):
    """Delete any per-user Jellyfin pull periodic tasks."""
    from django_celery_beat.models import PeriodicTask

    return PeriodicTask.objects.filter(
        _plex_watchlist_task_filter(user.id),
        task=tasks.JELLYFIN_PULL_TASK_NAME,
    ).delete()


def _ensure_arr_schedule(instance, task_name, source_label):
    """Create or enable the per-instance Radarr/Sonarr recurring schedule."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    user = instance.user
    next_sync_start = _next_arr_sync_start()
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=0,
        hour=f"*/{ARR_SYNC_INTERVAL_HOURS}",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )
    task_filter = PeriodicTask.objects.filter(
        _periodic_task_filter_for_instance(instance.id),
        task=task_name,
    )
    existing_task = task_filter.first()
    if existing_task:
        was_enabled = existing_task.enabled
        updated_fields = []
        desired_name = (
            f"Import from {source_label} ({instance.display_name} #{instance.id}) for "
            f"{user.username} (every {ARR_SYNC_INTERVAL_HOURS} hours)"
        )
        desired_kwargs = json.dumps({"instance_id": instance.id})
        if existing_task.name != desired_name:
            existing_task.name = desired_name
            updated_fields.append("name")
        if existing_task.crontab_id != crontab.id:
            existing_task.crontab = crontab
            updated_fields.append("crontab")
        if existing_task.interval_id is not None:
            existing_task.interval = None
            updated_fields.append("interval")
        if existing_task.clocked_id is not None:
            existing_task.clocked = None
            updated_fields.append("clocked")
        if existing_task.solar_id is not None:
            existing_task.solar = None
            updated_fields.append("solar")
        if existing_task.one_off:
            existing_task.one_off = False
            updated_fields.append("one_off")
        if existing_task.kwargs != desired_kwargs:
            existing_task.kwargs = desired_kwargs
            updated_fields.append("kwargs")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if existing_task.start_time is None or not was_enabled:
            existing_task.start_time = next_sync_start
            updated_fields.append("start_time")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task

    return PeriodicTask.objects.create(
        name=(
            f"Import from {source_label} ({instance.display_name} #{instance.id}) for "
            f"{user.username} (every {ARR_SYNC_INTERVAL_HOURS} hours)"
        ),
        task=task_name,
        crontab=crontab,
        kwargs=json.dumps({"instance_id": instance.id}),
        start_time=next_sync_start,
        enabled=True,
    )


def _ensure_lastfm_poll_schedule():
    """Create or update the shared Last.fm polling schedule."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    poll_interval_minutes = getattr(settings, "LASTFM_POLL_INTERVAL_MINUTES", 15)
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=poll_interval_minutes,
        period=IntervalSchedule.MINUTES,
    )
    task_name = f"Poll Last.fm for all users (every {poll_interval_minutes} minutes)"
    existing_task = PeriodicTask.objects.filter(
        task="Poll Last.fm for all users"
    ).first()

    if existing_task:
        updated_fields = []
        if existing_task.name != task_name:
            existing_task.name = task_name
            updated_fields.append("name")
        if existing_task.interval_id != interval.id:
            existing_task.interval = interval
            updated_fields.append("interval")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if existing_task.start_time is None:
            existing_task.start_time = timezone.now()
            updated_fields.append("start_time")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task, poll_interval_minutes

    return PeriodicTask.objects.create(
        name=task_name,
        task="Poll Last.fm for all users",
        interval=interval,
        start_time=timezone.now(),
        enabled=True,
    ), poll_interval_minutes


def _save_lastfm_history_reset(account, cutoff_uts: int):
    """Persist a fresh Last.fm history import state."""
    account.reset_history_import(cutoff_uts)
    account.save(
        update_fields=[
            "history_import_status",
            "history_import_cutoff_uts",
            "history_import_next_page",
            "history_import_total_pages",
            "history_import_started_at",
            "history_import_completed_at",
            "history_import_last_error_message",
        ],
    )


def _ensure_audiobookshelf_schedule(user):
    """Create or update the recurring Audiobookshelf import schedule for a user."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    poll_interval_minutes = getattr(
        settings, "AUDIOBOOKSHELF_POLL_INTERVAL_MINUTES", 15
    )
    interval, _ = IntervalSchedule.objects.get_or_create(
        every=poll_interval_minutes,
        period=IntervalSchedule.MINUTES,
    )
    task_name = (
        f"Import from Audiobookshelf for {user.username} "
        f"(every {poll_interval_minutes} minutes)"
    )
    existing_task = PeriodicTask.objects.filter(
        task=AUDIOBOOKSHELF_RECURRING_TASK_NAME,
        kwargs__regex=user_kwargs_regex(user.id),
    ).first()

    if existing_task:
        updated_fields = []
        if existing_task.name != task_name:
            existing_task.name = task_name
            updated_fields.append("name")
        if existing_task.interval_id != interval.id:
            existing_task.interval = interval
            updated_fields.append("interval")
        if existing_task.crontab_id is not None:
            existing_task.crontab = None
            updated_fields.append("crontab")
        if not existing_task.enabled:
            existing_task.enabled = True
            updated_fields.append("enabled")
        if updated_fields:
            existing_task.save(update_fields=updated_fields)
        return existing_task

    return PeriodicTask.objects.create(
        name=task_name,
        task=AUDIOBOOKSHELF_RECURRING_TASK_NAME,
        interval=interval,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=timezone.now(),
        enabled=True,
    )


def _ensure_storyteller_schedule(user):
    """Create the recurring Storyteller import schedule if missing."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    existing_task = PeriodicTask.objects.filter(
        task=STORYTELLER_RECURRING_TASK_NAME,
        kwargs__regex=user_kwargs_regex(user.id),
        enabled=True,
    ).first()
    if existing_task:
        return

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=0,
        hour="*/2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )
    PeriodicTask.objects.create(
        name=f"Import from Storyteller for {user.username} (every 2 hours)",
        task=STORYTELLER_RECURRING_TASK_NAME,
        crontab=crontab,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=timezone.now(),
        enabled=True,
    )


def _ensure_stremio_schedule(user):
    """Create the recurring Stremio import schedule if missing."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    existing_task = PeriodicTask.objects.filter(
        task=STREMIO_RECURRING_TASK_NAME,
        kwargs__regex=user_kwargs_regex(user.id),
        enabled=True,
    ).first()
    if existing_task:
        return

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=0,
        hour="*/2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )
    PeriodicTask.objects.create(
        name=f"Import from Stremio for {user.username} (every 2 hours)",
        task=STREMIO_RECURRING_TASK_NAME,
        crontab=crontab,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=timezone.now(),
        enabled=True,
    )


def _ensure_koito_poll_schedule(user):
    """Create the recurring Koito poll schedule for a user if missing."""
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    existing_task = PeriodicTask.objects.filter(
        task=tasks.KOITO_POLL_TASK_NAME,
        kwargs__regex=user_kwargs_regex(user.id),
        enabled=True,
    ).first()
    if existing_task:
        return

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute="*/15",
        hour="*",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )
    PeriodicTask.objects.create(
        name=f"Poll Koito for {user.username} (every 15 minutes)",
        task=tasks.KOITO_POLL_TASK_NAME,
        crontab=crontab,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=timezone.now(),
        enabled=True,
    )


def _ensure_two_hour_schedule(user, *, task_name, label):
    """Create a 2-hourly recurring import for a user if no enabled one exists.

    Returns True when a new schedule was created.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    existing_task = PeriodicTask.objects.filter(
        task=task_name,
        kwargs__regex=user_kwargs_regex(user.id),
        enabled=True,
    ).first()
    if existing_task:
        return False

    # Every 2 hours (0, 2, 4, ... 22).
    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=0,
        hour="*/2",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )
    PeriodicTask.objects.create(
        name=f"Import from {label} for {user.username} (every 2 hours)",
        task=task_name,
        crontab=crontab,
        kwargs=json.dumps({"user_id": user.id}),
        start_time=timezone.now(),
        enabled=True,
    )
    return True


# ---------------------------------------------------------------------------
# Radarr / Sonarr
# ---------------------------------------------------------------------------


def _connect_arr(user, *, label, model, client_cls, task_name, base_url, api_key, name):
    base_url = (base_url or "").strip()
    api_key = (api_key or "").strip()
    name = (name or "").strip()
    if not base_url or not api_key:
        msg = f"{label} base URL and API key are required."
        raise IntegrationError(msg)

    try:
        client_cls(base_url, api_key).healthcheck()
    except (helpers.MediaImportError, requests.RequestException) as exc:
        raise IntegrationError(
            f"Failed to connect to {label}.",
            unreachable=_arr_unreachable(exc),
            web_message=f"Failed to connect to {label}: {exc}",
        ) from exc

    try:
        instance = _run_with_lock_retry(
            f"create {label} instance",
            lambda: model.objects.create(
                user=user,
                name=name,
                base_url=base_url,
                api_key=helpers.encrypt(api_key),
            ),
        )
    except IntegrityError as exc:
        msg = f"You already have a {label} instance connected at this URL."
        raise IntegrationError(msg) from exc

    _ensure_arr_schedule(instance, task_name, label)
    getattr(tasks, f"import_{label.lower()}").delay(
        user_id=user.id, mode="new", instance_id=instance.id
    )
    return instance


def _get_arr_instance(user, model, label, instance_id):
    instance = model.objects.filter(pk=instance_id, user=user).first()
    if instance is None:
        msg = f"{label} instance not found."
        raise NotConnectedError(msg)
    return instance


def _disconnect_arr(user, *, label, model, task_name, source, instance_id):
    from django_celery_beat.models import PeriodicTask

    instance = _get_arr_instance(user, model, label, instance_id)

    def _disconnect():
        PeriodicTask.objects.filter(
            _periodic_task_filter_for_instance(instance.id),
            task=task_name,
        ).delete()
        CollectionSourceState.objects.filter(
            user=user, source=source, source_instance_id=instance.id
        ).delete()
        instance.delete()

    _run_with_lock_retry(f"disconnect {label}", _disconnect)


def _start_arr_import(user, *, label, model, task_name, instance_id):
    instance = _get_arr_instance(user, model, label, instance_id)
    result = getattr(tasks, f"import_{label.lower()}").delay(
        user_id=user.id, mode="new", instance_id=instance.id
    )
    _ensure_arr_schedule(instance, task_name, label)
    return result


def connect_radarr(user, base_url, api_key, name=""):
    """Validate and store a Radarr instance, enable its schedule, queue an import.

    Returns the RadarrInstance.
    """
    return _connect_arr(
        user,
        label="Radarr",
        model=RadarrInstance,
        client_cls=RadarrClient,
        task_name=RADARR_RECURRING_TASK_NAME,
        base_url=base_url,
        api_key=api_key,
        name=name,
    )


def disconnect_radarr(user, instance_id):
    """Remove one of the user's Radarr instances. Raises NotConnectedError."""
    _disconnect_arr(
        user,
        label="Radarr",
        model=RadarrInstance,
        task_name=RADARR_RECURRING_TASK_NAME,
        source="radarr",
        instance_id=instance_id,
    )


def start_radarr_import(user, instance_id):
    """Queue a Radarr import and ensure its schedule. Returns the AsyncResult."""
    return _start_arr_import(
        user,
        label="Radarr",
        model=RadarrInstance,
        task_name=RADARR_RECURRING_TASK_NAME,
        instance_id=instance_id,
    )


def connect_sonarr(user, base_url, api_key, name=""):
    """Validate and store a Sonarr instance, enable its schedule, queue an import.

    Returns the SonarrInstance.
    """
    return _connect_arr(
        user,
        label="Sonarr",
        model=SonarrInstance,
        client_cls=SonarrClient,
        task_name=SONARR_RECURRING_TASK_NAME,
        base_url=base_url,
        api_key=api_key,
        name=name,
    )


def disconnect_sonarr(user, instance_id):
    """Remove one of the user's Sonarr instances. Raises NotConnectedError."""
    _disconnect_arr(
        user,
        label="Sonarr",
        model=SonarrInstance,
        task_name=SONARR_RECURRING_TASK_NAME,
        source="sonarr",
        instance_id=instance_id,
    )


def start_sonarr_import(user, instance_id):
    """Queue a Sonarr import and ensure its schedule. Returns the AsyncResult."""
    return _start_arr_import(
        user,
        label="Sonarr",
        model=SonarrInstance,
        task_name=SONARR_RECURRING_TASK_NAME,
        instance_id=instance_id,
    )


# ---------------------------------------------------------------------------
# Plex
# ---------------------------------------------------------------------------


def disconnect_plex(user):
    """Remove stored Plex credentials, shares and the watchlist schedule."""

    def _disconnect():
        _disable_plex_watchlist_schedule(user)
        PlexWebhookShare.objects.filter(owner=user).delete()
        PlexAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Plex", _disconnect)


def disable_plex_watchlist(user):
    """Disable recurring Plex watchlist sync. Raises NotConnectedError."""
    plex_account = getattr(user, "plex_account", None)
    if not plex_account:
        msg = "Connect Plex before changing watchlist sync."
        raise NotConnectedError(msg)

    _disable_plex_watchlist_schedule(user)
    if plex_account.watchlist_sync_enabled:
        plex_account.watchlist_sync_enabled = False
        plex_account.save(update_fields=["watchlist_sync_enabled"])


PLEX_IMPORT_MODES = ("new", "overwrite", "watchlist", "update_collection")


def plex_library_values(plex_account):
    """Return the `machine::section` keys of the account's known libraries."""
    if not plex_account or not plex_account.plex_token:
        return set()
    return {
        f"{section.get('machine_identifier')}::{section.get('id')}"
        for section in (plex_account.sections or [])
        if section.get("machine_identifier") and section.get("id")
    }


def start_plex_import(user, *, libraries, mode, frequency, import_time):
    """Run or schedule a Plex import; return ImportQueued.

    `mode` "watchlist" turns on the recurring watchlist sync (outcome
    "scheduled"); "update_collection" refreshes collection metadata once;
    "new"/"overwrite" import history now (`frequency` "once") or on a
    schedule ("daily"/"2days" at `import_time`).
    """
    plex_account = getattr(user, "plex_account", None)
    if not plex_account:
        msg = "Connect Plex before importing."
        raise NotConnectedError(msg)
    if mode not in PLEX_IMPORT_MODES:
        msg = "Unknown Plex import mode."
        raise IntegrationError(msg)

    if mode == "watchlist":
        _ensure_plex_watchlist_schedule(user, plex_account)
        plex_account.watchlist_sync_enabled = True
        plex_account.save(update_fields=["watchlist_sync_enabled"])
        result = tasks.sync_plex_watchlist.delay(user_id=user.id, mode="watchlist")
        return ImportQueued(result=result, outcome="scheduled")

    if mode == "update_collection":
        if frequency != "once":
            msg = "Collection update mode only supports one-time execution."
            raise IntegrationError(msg)
        result = tasks.update_collection_metadata_from_plex.delay(
            library=libraries,
            user_id=user.id,
        )
        return ImportQueued(result=result)

    if frequency != "once":
        try:
            helpers.schedule_import(
                user,
                username=plex_account.plex_username or user.username,
                mode=mode,
                frequency=frequency,
                import_time=import_time,
                source="Plex",
                extra_kwargs={"library": libraries},
            )
        except helpers.ImportScheduleError as error:
            raise IntegrationError(str(error)) from error
        return ImportQueued(outcome="scheduled")

    result = tasks.import_plex.delay(library=libraries, user_id=user.id, mode=mode)
    return ImportQueued(result=result)


# ---------------------------------------------------------------------------
# Jellyfin
# ---------------------------------------------------------------------------


def connect_jellyfin(user, base_url, api_key, username=""):
    """Validate and store a Jellyfin account, then queue a history pull.

    Returns the JellyfinAccount.
    """
    base_url = (base_url or "").strip()
    api_key = (api_key or "").strip()
    username = (username or "").strip()
    if not base_url or not api_key:
        msg = "Jellyfin base URL and API key are required."
        raise IntegrationError(msg)

    client = JellyfinClient(base_url, api_key)
    try:
        client.healthcheck()
        current_user = client.get_current_user()
        if not current_user and username:
            current_user = client.find_user_by_name(username)
    except (JellyfinAuthError, JellyfinClientError) as exc:
        raise IntegrationError(
            "Failed to connect to Jellyfin.",
            unreachable=_jellyfin_unreachable(exc),
            web_message=f"Failed to connect to Jellyfin: {exc}",
        ) from exc

    if not current_user or not current_user.get("Id"):
        msg = (
            "Could not resolve a Jellyfin user for this API key. "
            "Dashboard API keys are not tied to a user, so enter the exact "
            "Jellyfin username in the username field and try again."
        )
        raise IntegrationError(msg)

    existing_account = getattr(user, "jellyfin_account", None)
    identity_changed = existing_account is not None and (
        existing_account.base_url != base_url
        or existing_account.jellyfin_user_id != current_user["Id"]
    )

    defaults = {
        "base_url": base_url,
        "api_key": helpers.encrypt(api_key),
        "jellyfin_user_id": current_user["Id"],
        "jellyfin_username": current_user.get("Name", ""),
        "connection_broken": False,
        "last_error_message": "",
    }
    if existing_account is None or identity_changed:
        # A different server/user invalidates any cached pull state: a
        # Playback Reporting rowid or "unavailable" result from the old
        # identity would otherwise silently carry over to the new one.
        defaults.update(
            {
                "playback_reporting_available": None,
                "playback_reporting_last_rowid": None,
                "library_backfill_completed_at": None,
            },
        )

    def _connect():
        account, _ = JellyfinAccount.objects.update_or_create(
            user=user,
            defaults=defaults,
        )
        if account.pull_history_enabled:
            _ensure_jellyfin_pull_schedule(user, account)
        return account

    account = _run_with_lock_retry("connect Jellyfin", _connect)

    # Seamless by default: queue an automatic history pull right away so a
    # newly connected user sees their watch history without any manual
    # export/upload step, and keep it running on a schedule going forward.
    tasks.pull_jellyfin_history.delay(user_id=user.id)
    return account


def disconnect_jellyfin(user):
    """Remove the Jellyfin account and its push/pull schedules."""

    def _disconnect():
        _disable_jellyfin_push_schedule(user)
        _disable_jellyfin_pull_schedule(user)
        JellyfinAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Jellyfin", _disconnect)


def update_jellyfin_settings(
    user,
    *,
    push_watched_enabled,
    push_unwatched_enabled,
    scheduled_push_enabled,
    instant_push_enabled,
    pull_history_enabled,
):
    """Update Jellyfin sync toggles and schedules. Returns the JellyfinAccount."""
    account = getattr(user, "jellyfin_account", None)
    if not account:
        msg = "Connect Jellyfin before changing sync settings."
        raise NotConnectedError(msg)

    account.push_watched_enabled = bool(push_watched_enabled)
    account.push_unwatched_enabled = bool(push_unwatched_enabled)
    account.scheduled_push_enabled = bool(scheduled_push_enabled)
    account.instant_push_enabled = bool(instant_push_enabled)
    account.pull_history_enabled = bool(pull_history_enabled)
    account.save(
        update_fields=[
            "push_watched_enabled",
            "push_unwatched_enabled",
            "scheduled_push_enabled",
            "instant_push_enabled",
            "pull_history_enabled",
        ],
    )

    if account.scheduled_push_enabled:
        _ensure_jellyfin_push_schedule(user, account)
    else:
        _disable_jellyfin_push_schedule(user)

    if account.pull_history_enabled:
        _ensure_jellyfin_pull_schedule(user, account)
    else:
        _disable_jellyfin_pull_schedule(user)

    return account


def push_jellyfin_now(user):
    """Queue an immediate Jellyfin watched-state push. Returns the AsyncResult."""
    account = getattr(user, "jellyfin_account", None)
    if not account:
        msg = "Connect Jellyfin before syncing."
        raise NotConnectedError(msg)

    return tasks.push_jellyfin_watched.delay(user_id=user.id, force=True)


def pull_jellyfin_now(user):
    """Queue an immediate Jellyfin history pull. Returns the AsyncResult."""
    account = getattr(user, "jellyfin_account", None)
    if not account or not account.is_connected:
        msg = "Connect Jellyfin before importing history."
        raise NotConnectedError(msg)

    return tasks.pull_jellyfin_history.delay(user_id=user.id)


# ---------------------------------------------------------------------------
# Audiobookshelf
# ---------------------------------------------------------------------------


def connect_audiobookshelf(user, base_url, api_token):
    """Validate and store an Audiobookshelf account and queue an import.

    Returns the AudiobookshelfAccount.
    """
    base_url = (base_url or "").strip()
    api_token = (api_token or "").strip()

    if not base_url or not api_token:
        msg = "Audiobookshelf base URL and API token are required."
        raise IntegrationError(msg)

    try:
        client = AudiobookshelfClient(base_url, api_token)
        client.get_me()
    except AudiobookshelfAuthError as exc:
        raise IntegrationError(
            "Audiobookshelf rejected the API token.",
            web_message=str(exc),
        ) from exc
    except Exception as exc:
        raise IntegrationError(
            "Failed to connect to Audiobookshelf.",
            unreachable=True,
            web_message=f"Failed to connect to Audiobookshelf: {exc}",
        ) from exc

    def _connect():
        account, _ = AudiobookshelfAccount.objects.update_or_create(
            user=user,
            defaults={
                "base_url": base_url,
                "api_token": helpers.encrypt(api_token),
                "connection_broken": False,
                "last_error_message": "",
            },
        )
        _ensure_audiobookshelf_schedule(user)
        return account

    account = _run_with_lock_retry("connect Audiobookshelf", _connect)
    tasks.import_audiobookshelf.delay(user_id=user.id, mode="new")
    return account


def disconnect_audiobookshelf(user):
    """Remove the Audiobookshelf account and its recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=AUDIOBOOKSHELF_RECURRING_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        AudiobookshelfAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Audiobookshelf", _disconnect)


def start_audiobookshelf_import(user):
    """Queue an Audiobookshelf import and ensure the schedule. Returns the AsyncResult."""
    account = getattr(user, "audiobookshelf_account", None)
    if not account:
        msg = "Connect Audiobookshelf before importing."
        raise NotConnectedError(msg)

    result = tasks.import_audiobookshelf.delay(user_id=user.id, mode="new")
    _ensure_audiobookshelf_schedule(user)
    return result


# ---------------------------------------------------------------------------
# Storyteller (device flow stays in the views)
# ---------------------------------------------------------------------------


def disconnect_storyteller(user):
    """Remove the Storyteller account and its recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=STORYTELLER_RECURRING_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        StorytellerAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Storyteller", _disconnect)


def start_storyteller_import(user):
    """Queue a Storyteller import and ensure the schedule. Returns the AsyncResult."""
    account = getattr(user, "storyteller_account", None)
    if not account:
        msg = "Connect Storyteller before importing."
        raise NotConnectedError(msg)

    result = tasks.import_storyteller.delay(user_id=user.id, mode="new")
    _ensure_storyteller_schedule(user)
    return result


# ---------------------------------------------------------------------------
# KOReader
# ---------------------------------------------------------------------------


def parse_finished_threshold_percent(raw):
    """Return a 0-1 completion threshold from a percentage string."""
    raw = (raw or "").strip()
    if not raw:
        return 1.0
    try:
        percent = float(raw)
    except ValueError as exc:
        msg = "Completion threshold must be a number between 1 and 100."
        raise ValueError(msg) from exc
    if not 1 <= percent <= KOREADER_MAX_COMPLETION:
        msg = "Completion threshold must be between 1 and 100 percent."
        raise ValueError(msg)
    return percent / 100.0


def _koreader_options(
    verify_ssl, create_missing, skip_finished_books, finished_threshold_percent
):
    try:
        finished_threshold = parse_finished_threshold_percent(
            finished_threshold_percent
        )
    except ValueError as exc:
        raise IntegrationError(str(exc)) from exc
    return {
        "verify_ssl": bool(verify_ssl),
        "create_missing": bool(create_missing),
        "skip_finished_books": bool(skip_finished_books),
        "finished_threshold": finished_threshold,
    }


def _validate_koreader_connection(server_url, username, auth_key, verify_ssl):
    """Verify credentials against the sync server or raise."""
    client = KoreaderClient(server_url, username, auth_key, verify_ssl=verify_ssl)
    client.auth()


def _validate_koreader_or_raise(server_url, username, auth_key, verify_ssl):
    try:
        _validate_koreader_connection(server_url, username, auth_key, verify_ssl)
    except KoreaderAuthError as exc:
        raise IntegrationError(
            "KOReader rejected the credentials.",
            web_message=str(exc),
        ) from exc
    except (KoreaderClientError, requests.RequestException) as exc:
        raise IntegrationError(
            "Could not reach KOReader sync server.",
            unreachable=True,
            web_message=f"Could not reach KOReader sync server: {exc}",
        ) from exc


def connect_koreader(
    user,
    server_url,
    username,
    password,
    *,
    verify_ssl=False,
    create_missing=False,
    skip_finished_books=False,
    finished_threshold_percent="",
):
    """Validate and store a KOReader sync account. Returns the KoreaderAccount.

    Does not queue an import; call ``start_koreader_import`` for that.
    """
    options = _koreader_options(
        verify_ssl, create_missing, skip_finished_books, finished_threshold_percent
    )
    server_url = (server_url or "").strip().rstrip("/")
    username = (username or "").strip()
    password = password or ""

    if not server_url or not username or not password:
        msg = "Server URL, username, and password are required."
        raise IntegrationError(msg)

    auth_key = KoreaderClient.password_to_auth_key(password)
    _validate_koreader_or_raise(server_url, username, auth_key, options["verify_ssl"])

    account, _ = _run_with_lock_retry(
        "connect KOReader",
        lambda: KoreaderAccount.objects.update_or_create(
            user=user,
            defaults={
                "server_url": server_url,
                "username": username,
                "auth_key": helpers.encrypt(auth_key),
                **options,
                "connection_broken": False,
                "last_error_message": "",
            },
        ),
    )
    return account


def update_koreader_settings(
    user,
    server_url,
    username,
    password="",
    *,
    verify_ssl=False,
    create_missing=False,
    skip_finished_books=False,
    finished_threshold_percent="",
):
    """Update KOReader connection and sync options. Returns the KoreaderAccount."""
    account = getattr(user, "koreader_account", None)
    if not account:
        msg = "Connect KOReader before changing settings."
        raise NotConnectedError(msg)

    server_url = (server_url or "").strip().rstrip("/")
    username = (username or "").strip()
    password = password or ""
    options = _koreader_options(
        verify_ssl, create_missing, skip_finished_books, finished_threshold_percent
    )

    if not server_url or not username:
        msg = "Server URL and username are required."
        raise IntegrationError(msg)

    if password:
        auth_key = KoreaderClient.password_to_auth_key(password)
    else:
        try:
            auth_key = helpers.decrypt_or_raise(account.auth_key)
        except helpers.MediaImportError as exc:
            raise IntegrationError(
                "Could not read the saved KOReader credentials.",
                web_message=str(exc),
            ) from exc

    _validate_koreader_or_raise(server_url, username, auth_key, options["verify_ssl"])

    account.server_url = server_url
    account.username = username
    account.auth_key = helpers.encrypt(auth_key)
    account.verify_ssl = options["verify_ssl"]
    account.create_missing = options["create_missing"]
    account.skip_finished_books = options["skip_finished_books"]
    account.finished_threshold = options["finished_threshold"]
    account.connection_broken = False
    account.last_error_message = ""
    account.save(
        update_fields=[
            "server_url",
            "username",
            "auth_key",
            "verify_ssl",
            "create_missing",
            "skip_finished_books",
            "finished_threshold",
            "connection_broken",
            "last_error_message",
            "updated_at",
        ],
    )
    return account


def disconnect_koreader(user):
    """Remove the KOReader account, document links and recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=KOREADER_IMPORT_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        KoreaderDocumentLink.objects.filter(user=user).delete()
        KoreaderAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect KOReader", _disconnect)


def queue_koreader_import(user, mode):
    """Queue a one-off KOReader import without checking the account."""
    return tasks.import_koreader.delay(user_id=user.id, mode=mode)


def start_koreader_import(user, mode):
    """Queue a one-off KOReader import. Returns the AsyncResult.

    Recurring schedules are created by the caller via
    ``helpers.create_import_schedule``.
    """
    account = getattr(user, "koreader_account", None)
    if not account:
        msg = "Connect KOReader before importing."
        raise NotConnectedError(msg)

    return queue_koreader_import(user, mode)


# ---------------------------------------------------------------------------
# Stremio
# ---------------------------------------------------------------------------


def connect_stremio(user, email="", password="", auth_key=""):
    """Validate and store a Stremio account, then queue an import.

    Returns the StremioAccount.
    """
    email = (email or "").strip()
    password = (password or "").strip()
    auth_key = (auth_key or "").strip()

    if not auth_key and not (email and password):
        msg = "Enter your Stremio email and password, or an auth key."
        raise IntegrationError(msg)

    try:
        if not auth_key:
            auth_key = stremio.login(email, password)
        else:
            # Validate a pasted auth key before storing it.
            stremio.get_user(auth_key)
    except helpers.MediaImportError as error:
        logger.exception("Stremio login failed")
        raise IntegrationError(
            "Could not connect to Stremio. Check your credentials; for accounts "
            "created via Facebook login, paste an auth key instead or set a "
            "password first.",
            web_message=(
                "Could not connect to Stremio. Check your credentials; for accounts "
                "created via Facebook login, paste an auth key instead or set a "
                f"password first. ({error})"
            ),
        ) from error
    except Exception as error:
        logger.exception("Failed to connect to Stremio")
        raise IntegrationError(
            "Failed to connect to Stremio.",
            unreachable=True,
            web_message=f"Failed to connect to Stremio: {error}",
        ) from error

    def _connect():
        account, _ = StremioAccount.objects.update_or_create(
            user=user,
            defaults={
                "auth_key": helpers.encrypt(auth_key),
                "email": helpers.encrypt(email) if email else "",
                "connection_broken": False,
                "last_error_message": "",
            },
        )
        _ensure_stremio_schedule(user)
        return account

    account = _run_with_lock_retry("connect Stremio", _connect)
    tasks.import_stremio.delay(user_id=user.id, mode="new")
    return account


def disconnect_stremio(user):
    """Remove the Stremio account and its recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=STREMIO_RECURRING_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        StremioAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Stremio", _disconnect)


def start_stremio_import(user):
    """Queue a Stremio import and ensure the schedule. Returns the AsyncResult."""
    account = getattr(user, "stremio_account", None)
    if not account:
        msg = "Connect Stremio before importing."
        raise NotConnectedError(msg)

    result = tasks.import_stremio.delay(user_id=user.id, mode="new")
    _ensure_stremio_schedule(user)
    return result


# ---------------------------------------------------------------------------
# Xbox / PlayStation Network
# ---------------------------------------------------------------------------


def _next_crontab_run(crontab):
    """Return the next fire time for a crontab schedule.

    New periodic tasks are created with this as their `start_time`; beat
    treats a task whose `start_time` has already passed as due immediately,
    which would run the import once on creation and again on schedule.
    """
    schedule_timezone = zoneinfo.ZoneInfo(str(crontab.timezone))
    cron_expression = (
        f"{crontab.minute} {crontab.hour} {crontab.day_of_month} "
        f"{crontab.month_of_year} {crontab.day_of_week}"
    )
    now = timezone.now().astimezone(schedule_timezone)
    return croniter.croniter(cron_expression, now).get_next(datetime)


def _console_schedule_name(source, user, parsed_time, frequency):
    """Name a user's console schedule for the beat admin and the schedule list."""
    return f"Import from {source} for {user.username} at {parsed_time} {frequency}"


def _reclaim_console_schedule_name(source, task_name, parsed_time, frequency):
    """Free a schedule name whose holder no longer answers to it.

    `PeriodicTask.name` is unique and these names are built from the
    username, which can be changed and freed for someone else to take — so
    a name outlives its owner's claim to it. The kwargs `user_id` is the
    real owner: rename the holder to match whoever that is now, or drop it
    if that user is gone. Returns whether the name is ours to take.
    """
    from django_celery_beat.models import PeriodicTask

    holder = PeriodicTask.objects.filter(name=task_name).first()
    if holder is None:
        return True

    try:
        holder_user_id = json.loads(holder.kwargs or "{}").get("user_id")
    except (TypeError, ValueError):
        holder_user_id = None

    holder_user = (
        users.models.User.objects.filter(id=holder_user_id).first()
        if holder_user_id
        else None
    )
    if holder_user is None:
        holder.delete()
        return True

    current_name = _console_schedule_name(source, holder_user, parsed_time, frequency)
    if current_name == task_name:
        # The holder is entitled to the name; it just isn't ours.
        return False

    holder.name = current_name
    holder.save(update_fields=["name"])
    return True


def _create_console_schedule(
    user,
    source,
    recurring_task_name,
    mode,
    frequency,
    import_time,
):
    """Create a recurring console import schedule for the chosen time.

    Returns "scheduled" or "reenabled"; raises IntegrationError otherwise.
    """
    from django_celery_beat.models import CrontabSchedule, PeriodicTask

    try:
        parsed_time = datetime.strptime(import_time, "%H:%M").time()  # noqa: DTZ007  # wall-clock value; the crontab carries the timezone
    except (TypeError, ValueError) as exc:
        msg = "Invalid import time."
        raise IntegrationError(msg) from exc

    crontab, _ = CrontabSchedule.objects.get_or_create(
        minute=parsed_time.minute,
        hour=parsed_time.hour,
        day_of_week=CONSOLE_RECURRING_FREQUENCIES[frequency],
        day_of_month="*",
        month_of_year="*",
        timezone=timezone.get_default_timezone(),
    )

    task_name = _console_schedule_name(source, user, parsed_time, frequency)
    desired_kwargs = json.dumps({"user_id": user.id, "mode": mode})
    existing_task = (
        PeriodicTask.objects.filter(
            _periodic_task_filter_for_user(user.id),
            task=recurring_task_name,
            crontab=crontab,
        )
        .order_by("-enabled", "id")
        .first()
    )
    already_scheduled = "The same import task is already scheduled."
    if existing_task:
        if existing_task.enabled:
            raise IntegrationError(already_scheduled)

        # A disabled task still owns its unique name, so revive it instead of
        # creating a second one that would collide.
        existing_task.name = task_name
        existing_task.kwargs = desired_kwargs
        existing_task.start_time = _next_crontab_run(crontab)
        existing_task.enabled = True
        existing_task.save(
            update_fields=["name", "kwargs", "start_time", "enabled"],
        )
        return "reenabled"

    if not _reclaim_console_schedule_name(source, task_name, parsed_time, frequency):
        raise IntegrationError(already_scheduled)

    try:
        PeriodicTask.objects.create(
            name=task_name,
            task=recurring_task_name,
            crontab=crontab,
            kwargs=desired_kwargs,
            start_time=_next_crontab_run(crontab),
            enabled=True,
        )
    except IntegrityError as exc:
        logger.exception("%s schedule %s could not be created", source, task_name)
        raise IntegrationError(already_scheduled) from exc

    return "scheduled"


def start_console_import(
    user,
    label,
    task,
    recurring_task_name,
    *,
    mode,
    frequency,
    time,
):
    """Queue a one-off console import, or schedule a recurring one.

    A scheduled import only runs on its schedule; a one time import runs
    straight away and creates no periodic task. Returns an ``ImportQueued``
    whose ``outcome`` is "queued", "scheduled" or "reenabled"; ``result`` is the
    AsyncResult for a queued run and None otherwise.
    """
    if frequency not in CONSOLE_RECURRING_FREQUENCIES:
        result = task.delay(user_id=user.id, mode=mode)
        return ImportQueued(result=result, outcome="queued")

    outcome = _create_console_schedule(
        user,
        label,
        recurring_task_name,
        mode,
        frequency,
        time,
    )
    return ImportQueued(result=None, outcome=outcome)


def _console_error(label_text, error):
    """Map a MediaImportError from a console login to an IntegrationError."""
    return IntegrationError(
        f"Could not connect to {label_text}.",
        unreachable=_console_unreachable(error),
        web_message=f"Could not connect to {label_text}: {error}",
    )


def _console_unexpected_error(label_text, error):
    return IntegrationError(
        f"Failed to connect to {label_text} ({exception_summary(error)}). "
        "Check the logs for details.",
        unreachable=True,
    )


def connect_xbox(user, api_key):
    """Validate and store an Xbox (OpenXBL) account. Returns the XboxAccount."""
    api_key = (api_key or "").strip()
    if not api_key:
        msg = "An OpenXBL API key is required."
        raise IntegrationError(msg)

    try:
        xuid, gamertag = xbox_api.get_account(api_key)
    except helpers.MediaImportError as error:
        raise _console_error("Xbox", error) from error
    except Exception as error:
        logger.exception("Failed to connect to Xbox")
        raise _console_unexpected_error("Xbox", error) from error

    account, _ = _run_with_lock_retry(
        "connect Xbox",
        lambda: XboxAccount.objects.update_or_create(
            user=user,
            defaults={
                "api_key": helpers.encrypt(api_key),
                "xuid": xuid,
                "gamertag": gamertag,
                "connection_broken": False,
                "last_error_message": "",
            },
        ),
    )
    return account


def disconnect_xbox(user):
    """Remove the Xbox account and its recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            _periodic_task_filter_for_user(user.id),
            task=XBOX_RECURRING_TASK_NAME,
        ).delete()
        XboxAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Xbox", _disconnect)


def start_xbox_import(user, *, mode, frequency, time):
    """Queue or schedule an Xbox import. Returns an ``ImportQueued``."""
    account = getattr(user, "xbox_account", None)
    if not account:
        msg = "Connect Xbox before importing."
        raise NotConnectedError(msg)

    return start_console_import(
        user,
        "Xbox",
        tasks.import_xbox,
        XBOX_RECURRING_TASK_NAME,
        mode=mode,
        frequency=frequency,
        time=time,
    )


def connect_psn(user, npsso):
    """Validate and store a PlayStation Network account. Returns the PSNAccount."""
    npsso = (npsso or "").strip()
    if not npsso:
        msg = "A PSN NPSSO token is required."
        raise IntegrationError(msg)

    try:
        account_id, online_id = psn_api.get_account(npsso)
    except helpers.MediaImportError as error:
        raise _console_error("PlayStation Network", error) from error
    except Exception as error:
        logger.exception("Failed to connect to PlayStation Network")
        raise _console_unexpected_error("PlayStation Network", error) from error

    account, _ = _run_with_lock_retry(
        "connect PSN",
        lambda: PSNAccount.objects.update_or_create(
            user=user,
            defaults={
                "npsso": helpers.encrypt(npsso),
                "account_id": account_id,
                "online_id": online_id,
                "connection_broken": False,
                "last_error_message": "",
            },
        ),
    )
    return account


def disconnect_psn(user):
    """Remove the PSN account and its recurring import."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            _periodic_task_filter_for_user(user.id),
            task=PSN_RECURRING_TASK_NAME,
        ).delete()
        PSNAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect PSN", _disconnect)


def start_psn_import(user, *, mode, frequency, time):
    """Queue or schedule a PSN import. Returns an ``ImportQueued``."""
    account = getattr(user, "psn_account", None)
    if not account:
        msg = "Connect PlayStation Network before importing."
        raise NotConnectedError(msg)

    return start_console_import(
        user,
        "PSN",
        tasks.import_psn,
        PSN_RECURRING_TASK_NAME,
        mode=mode,
        frequency=frequency,
        time=time,
    )


# ---------------------------------------------------------------------------
# Pocket Casts
# ---------------------------------------------------------------------------


def connect_pocketcasts(user, email, password):
    """Validate and store a Pocket Casts account.

    Returns the PocketCastsAccount with a transient ``initial_import_queued``
    attribute: True when a new recurring schedule was created and the initial
    import queued.
    """
    email = (email or "").strip()
    password = (password or "").strip()

    if not email:
        msg = "Email is required."
        raise IntegrationError(msg)

    if not password:
        msg = "Password is required."
        raise IntegrationError(msg)

    # Attempt to login with credentials
    try:
        logger.debug("Attempting Pocket Casts login with configured credentials")
        login_response = pocketcasts_api.login(email, password)
        access_token = login_response["accessToken"]
        refresh_token = login_response.get("refreshToken", "")

        logger.info("Successfully logged in to Pocket Casts for user %s", user.username)
    except PocketCastsAuthError as exc:
        logger.exception("Pocket Casts login failed")
        msg = (
            "Invalid email or password. For accounts created via 'Sign in with Apple' or 'Sign in with Google', "
            "please set a password first using Pocket Casts' 'Forgot Password' feature, then enter your email and new password here."
        )
        raise IntegrationError(msg) from exc
    except Exception as exc:
        logger.exception("Failed to login to Pocket Casts")
        raise IntegrationError(
            "Failed to connect to Pocket Casts.",
            unreachable=True,
            web_message=f"Failed to connect to Pocket Casts: {exc}",
        ) from exc

    # Encrypt and store credentials and tokens
    try:
        encrypted_email = helpers.encrypt(email)
        encrypted_password = helpers.encrypt(password)
        encrypted_access = helpers.encrypt(access_token)
        encrypted_refresh = helpers.encrypt(refresh_token) if refresh_token else None

        # Parse expiration from JWT
        token_expires_at = pocketcasts_api.parse_token_expiration(access_token)

        def _connect():
            account, _ = PocketCastsAccount.objects.update_or_create(
                user=user,
                defaults={
                    "email": encrypted_email,
                    "password": encrypted_password,
                    "access_token": encrypted_access,
                    "refresh_token": encrypted_refresh,
                    "token_expires_at": token_expires_at,
                    "connection_broken": False,  # Clear broken flag on successful connection
                },
            )

            # Set up 2-hour recurring import if it doesn't exist
            newly_scheduled = _ensure_two_hour_schedule(
                user,
                task_name=POCKETCASTS_RECURRING_TASK_NAME,
                label="Pocket Casts",
            )
            return account, newly_scheduled

        account, newly_scheduled = _run_with_lock_retry("connect Pocket Casts", _connect)

        if newly_scheduled:
            # Run initial import
            tasks.import_pocketcasts.delay(
                user_id=user.id,
                mode="new",
            )
    except Exception as exc:
        logger.exception("Failed to store Pocket Casts credentials")
        raise IntegrationError(
            "Failed to store credentials.",
            web_message=f"Failed to store credentials: {exc}",
        ) from exc

    account.initial_import_queued = newly_scheduled
    return account


def disconnect_pocketcasts(user):
    """Remove stored Pocket Casts credentials and delete the periodic import task."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        # Delete periodic import task if it exists
        PeriodicTask.objects.filter(
            task=POCKETCASTS_RECURRING_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()

        # Clear all credentials (full disconnect)
        PocketCastsAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Pocket Casts", _disconnect)


def start_pocketcasts_import(user):
    """Queue a Pocket Casts import, creating the 2-hourly schedule if missing.

    Pocket Casts always uses mode="new". Returns an ``ImportQueued`` whose
    ``schedule_created`` is True when the recurring schedule was just created.
    """
    pocketcasts_account = getattr(user, "pocketcasts_account", None)
    if not pocketcasts_account:
        msg = "Connect Pocket Casts before importing."
        raise NotConnectedError(msg)

    # Refresh from DB to get latest status
    pocketcasts_account.refresh_from_db()

    # Allow sync even if connection is broken - importer will attempt refresh
    from django_celery_beat.models import PeriodicTask

    existing_task = PeriodicTask.objects.filter(
        task=POCKETCASTS_RECURRING_TASK_NAME,
        kwargs__regex=user_kwargs_regex(user.id),
        enabled=True,
    ).first()

    # First import - run immediately, then set up 2-hour schedule
    result = tasks.import_pocketcasts.delay(user_id=user.id, mode="new")
    if existing_task:
        return ImportQueued(result=result, schedule_created=False)

    _ensure_two_hour_schedule(
        user, task_name=POCKETCASTS_RECURRING_TASK_NAME, label="Pocket Casts"
    )
    return ImportQueued(result=result, schedule_created=True)


# ---------------------------------------------------------------------------
# GPodder
# ---------------------------------------------------------------------------


def connect_gpodder(user, server_url, username, password, device_filter=""):
    """Validate and store a GPodder account.

    Returns the GPodderAccount with a transient ``initial_import_queued``
    attribute: True when a new recurring schedule was created and the initial
    sync queued.
    """
    server_url = gpodder_api.normalize_server_url(server_url or "")
    username = (username or "").strip()
    password = (password or "").strip()
    device_filter = (device_filter or "").strip()

    if not username:
        msg = "Username is required."
        raise IntegrationError(msg)

    if not password:
        msg = "Password is required."
        raise IntegrationError(msg)

    gpodder_credentials = gpodder_api.GPodderCredentials(
        server_url=server_url,
        username=username,
        password=password,
    )
    try:
        gpodder_api.verify_login(gpodder_credentials)
    except GPodderAuthError as exc:
        msg = "Invalid GPodder username or password."
        raise IntegrationError(msg) from exc
    except GPodderClientError as exc:
        raise IntegrationError(
            "Failed to connect to GPodder.",
            unreachable=True,
            web_message=f"Failed to connect to GPodder: {exc}",
        ) from exc

    # Device id stays "yamtrack-<id>": it is registered on the remote
    # GPodder server, and a new id would start a fresh sync from scratch.
    device_id = f"yamtrack-{user.id}"

    try:

        def _connect():
            account, _ = GPodderAccount.objects.update_or_create(
                user=user,
                defaults={
                    "server_url": helpers.encrypt(server_url),
                    "username": helpers.encrypt(username),
                    "password": helpers.encrypt(password),
                    "device_id": device_id,
                    "device_filter": device_filter,
                    "connection_broken": False,
                    "last_error_message": "",
                },
            )
            newly_scheduled = _ensure_two_hour_schedule(
                user, task_name=GPODDER_RECURRING_TASK_NAME, label="GPodder"
            )
            return account, newly_scheduled

        account, newly_scheduled = _run_with_lock_retry("connect GPodder", _connect)

        if newly_scheduled:
            tasks.import_gpodder.delay(user_id=user.id, mode="new")
    except Exception as exc:
        logger.exception("Failed to store GPodder credentials")
        raise IntegrationError(
            "Failed to save GPodder connection.",
            web_message=f"Failed to save GPodder connection: {exc}",
        ) from exc

    account.initial_import_queued = newly_scheduled
    return account


def disconnect_gpodder(user):
    """Remove stored GPodder credentials and scheduled imports."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=GPODDER_RECURRING_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        GPodderAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect GPodder", _disconnect)


def start_gpodder_import(user):
    """Queue a GPodder sync, creating the 2-hourly schedule if missing.

    Returns an ``ImportQueued`` whose ``schedule_created`` is True when the
    recurring schedule was just created.
    """
    gpodder_account = getattr(user, "gpodder_account", None)
    if not gpodder_account:
        msg = "Connect GPodder before syncing."
        raise NotConnectedError(msg)

    gpodder_account.refresh_from_db()

    schedule_created = _ensure_two_hour_schedule(
        user, task_name=GPODDER_RECURRING_TASK_NAME, label="GPodder"
    )
    result = tasks.import_gpodder.delay(user_id=user.id, mode="new")
    return ImportQueued(result=result, schedule_created=schedule_created)


# ---------------------------------------------------------------------------
# Last.fm
# ---------------------------------------------------------------------------


def connect_lastfm(user, username):
    """Validate a Last.fm username, store it and queue the first syncs.

    Returns the LastFMAccount.
    """
    username = (username or "").strip()

    if not username:
        msg = "Last.fm username is required."
        raise IntegrationError(msg)

    # Validate username by making a test API call
    try:
        logger.debug("Validating Last.fm username: %s", username)
        # Make a minimal API call to verify user exists and has public scrobbles
        lastfm_api.get_recent_tracks(username=username, limit=1, page=1)
        logger.info("Successfully validated Last.fm username: %s", username)
    except LastFMClientError as exc:
        logger.exception("Last.fm username validation failed")
        msg = "Invalid Last.fm username or user not found. Please check your username and ensure your scrobbles are public."
        raise IntegrationError(msg) from exc
    except LastFMRateLimitError as exc:
        logger.exception("Last.fm rate limit during validation")
        raise IntegrationError(
            "Last.fm API rate limit exceeded. Please try again in a few moments.",
            unreachable=True,
        ) from exc
    except LastFMAPIError as exc:
        logger.exception("Last.fm API error during validation")
        raise IntegrationError(
            "Failed to connect to Last.fm.",
            unreachable=True,
            web_message=f"Failed to connect to Last.fm: {exc}",
        ) from exc
    except Exception as exc:
        logger.exception("Unexpected error validating Last.fm username")
        raise IntegrationError(
            "Failed to connect to Last.fm.",
            unreachable=True,
            web_message=f"Failed to connect to Last.fm: {exc}",
        ) from exc

    # Store username and initialize sync state
    try:
        current_timestamp = int(time.time())

        def _connect():
            lastfm_account, _ = LastFMAccount.objects.update_or_create(
                user=user,
                defaults={
                    "lastfm_username": username,
                    "last_fetch_timestamp_uts": current_timestamp,
                    "connection_broken": False,
                    "failure_count": 0,
                    "last_error_code": "",
                    "last_error_message": "",
                    "last_failed_at": None,
                },
            )
            _save_lastfm_history_reset(lastfm_account, current_timestamp - 1)
            _ensure_lastfm_poll_schedule()
            return lastfm_account

        account = _run_with_lock_retry("connect Last.fm", _connect)
        tasks.poll_lastfm_for_user.delay(user_id=user.id)
        tasks.import_lastfm_history.delay(user_id=user.id, reset=False)
    except Exception as exc:
        logger.exception("Failed to store Last.fm connection")
        raise IntegrationError(
            "Failed to save Last.fm connection.",
            web_message=f"Failed to save Last.fm connection: {exc}",
        ) from exc

    return account


def disconnect_lastfm(user):
    """Remove the Last.fm connection and flag any in-flight import to cancel."""
    from integrations.models import ImportRun

    LastFMAccount.objects.filter(user=user).delete()
    # Deleting the account already stops future self-requeued chunks (they
    # no-op when the account is gone), but flag any in-flight run too so
    # the cooperative cancel check picks it up before its next requeue.
    ImportRun.objects.filter(
        user=user,
        source="lastfm",
        status=ImportRun.Status.RUNNING,
    ).update(cancel_requested=True)

    # If no users left, we could disable the periodic task, but we'll leave it
    # running - it will just skip if no users are connected
    # This allows the task to stay configured for future users


def _connected_lastfm_account(user, missing_message):
    lastfm_account = getattr(user, "lastfm_account", None)
    if not lastfm_account:
        raise NotConnectedError(missing_message)

    lastfm_account.refresh_from_db()
    if not lastfm_account.is_connected:
        msg = "Last.fm connection is broken. Please reconnect."
        raise NotConnectedError(msg)
    return lastfm_account


def poll_lastfm_now(user):
    """Queue a Last.fm poll for the user. Returns the AsyncResult."""
    _connected_lastfm_account(user, "Connect Last.fm before syncing.")
    return tasks.poll_lastfm_for_user.delay(user_id=user.id)


def start_lastfm_history_import(user):
    """Queue or rerun a full Last.fm history import. Returns the AsyncResult.

    Raises AlreadyRunningError when one is already active.
    """
    lastfm_account = _connected_lastfm_account(
        user, "Connect Last.fm before importing history."
    )

    if lastfm_account.history_import_is_active:
        msg = "Full Last.fm history import already running."
        raise AlreadyRunningError(msg)

    cutoff_uts = (lastfm_account.last_fetch_timestamp_uts or int(time.time())) - 1
    _save_lastfm_history_reset(lastfm_account, cutoff_uts)
    return tasks.import_lastfm_history.delay(user_id=user.id, reset=False)


# ---------------------------------------------------------------------------
# Koito
# ---------------------------------------------------------------------------


def connect_koito(user, base_url, api_key):
    """Validate and store a Koito account and queue the first syncs.

    Returns the KoitoAccount.
    """
    base_url = (base_url or "").strip().rstrip("/")
    api_key = (api_key or "").strip()

    if not base_url or not api_key:
        msg = "Koito server URL and API key are required."
        raise IntegrationError(msg)

    try:
        koito_api.validate_connection(base_url, api_key)
    except koito_api.KoitoAuthError as exc:
        raise IntegrationError(
            "Koito rejected the API key.",
            web_message=str(exc),
        ) from exc
    except Exception as exc:
        raise IntegrationError(
            "Failed to connect to Koito.",
            unreachable=True,
            web_message=f"Failed to connect to Koito: {exc}",
        ) from exc

    def _connect():
        account, _ = KoitoAccount.objects.update_or_create(
            user=user,
            defaults={
                "base_url": base_url,
                "api_key": helpers.encrypt(api_key),
                "last_fetch_timestamp_uts": int(timezone.now().timestamp()),
                "connection_broken": False,
                "failure_count": 0,
                "last_error_message": "",
                "last_failed_at": None,
            },
        )
        _ensure_koito_poll_schedule(user)
        return account

    account = _run_with_lock_retry("connect Koito", _connect)
    tasks.poll_koito_for_user.delay(user_id=user.id)
    tasks.import_koito_history.delay(user_id=user.id, reset=True)
    return account


def disconnect_koito(user):
    """Remove the Koito account and its recurring poll."""
    from django_celery_beat.models import PeriodicTask

    def _disconnect():
        PeriodicTask.objects.filter(
            task=tasks.KOITO_POLL_TASK_NAME,
            kwargs__regex=user_kwargs_regex(user.id),
        ).delete()
        KoitoAccount.objects.filter(user=user).delete()

    _run_with_lock_retry("disconnect Koito", _disconnect)


def _connected_koito_account(user, missing_message):
    koito_account = getattr(user, "koito_account", None)
    if not koito_account:
        raise NotConnectedError(missing_message)

    koito_account.refresh_from_db()
    if not koito_account.is_connected:
        msg = "Koito connection is broken. Please reconnect."
        raise NotConnectedError(msg)
    return koito_account


def poll_koito_now(user):
    """Queue a Koito sync for the user. Returns the AsyncResult."""
    _connected_koito_account(user, "Connect Koito before syncing.")
    return tasks.poll_koito_for_user.delay(user_id=user.id)


def start_koito_history_import(user):
    """Queue or rerun a full Koito history import. Returns the AsyncResult.

    Raises AlreadyRunningError when one is already active.
    """
    koito_account = _connected_koito_account(
        user, "Connect Koito before importing history."
    )

    if koito_account.history_import_is_active:
        msg = "Full Koito history import already running."
        raise AlreadyRunningError(msg)

    return tasks.import_koito_history.delay(user_id=user.id, reset=True)
