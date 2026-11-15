"""Import runs and import/export schedules, shared by the web and the API (P1-H)."""

import datetime as dt
import json
import re
import uuid

from django.apps import apps
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from app.models import MediaTypes
from integrations.models import ImportRun, LastFMAccount, PlexAccount
from integrations.plex_watchlist import WATCHLIST_TASK_NAME

LASTFM_POLL_TASK = "Poll Last.fm for all users"
EXPORT_TASK = "Scheduled backup export"
EXPORT_FREQUENCIES = {"daily": "*", "2days": "*/2", "weekly": "0"}


class DataManagementError(ValueError):
    """The request cannot be carried out; the message says why."""


def task_belongs_to_user(task, user):
    """Return whether a periodic task's kwargs name exactly this user.

    A plain substring test reads `"user_id": 1` out of `"user_id": 11`, so
    the id has to be anchored on the delimiter that follows it. Quoting and
    spacing vary with how the kwargs were written.
    """
    if not task.kwargs:
        return False
    return bool(
        re.search(
            rf"""['"]user_id['"]:\s*{user.id}\s*[,}}]""",
            task.kwargs,
        ),
    )


def cancel_import_run(run):
    """Stop a running import.

    Single-task importers are revoked outright; Last.fm and Koito backfills
    reschedule themselves, so they stop cooperatively on `cancel_requested`.
    """
    from config.celery import app as celery_app

    if run.status != ImportRun.Status.RUNNING:
        msg = "This import is not running."
        raise DataManagementError(msg)
    if run.task_id:
        celery_app.control.revoke(run.task_id, terminate=True)
    ImportRun.objects.filter(id=run.id).update(
        status=ImportRun.Status.CANCELLED,
        cancel_requested=True,
        finished_at=timezone.now(),
    )


def rollback_import_run(run, user):
    """Undo the media rows one import run created; return (deleted, reverted).

    Music rows are changed in place by each play, so they get a history-based
    revert instead of a delete that could take other runs' plays with them.
    """
    from app.services.music_scrobble import revert_music_import_run

    if run.status == ImportRun.Status.RUNNING:
        msg = "Cancel the import before rolling it back."
        raise DataManagementError(msg)
    total_deleted = 0
    for media_type in MediaTypes.values:
        if media_type in (MediaTypes.EPISODE.value, MediaTypes.MUSIC.value):
            continue
        model = apps.get_model(app_label="app", model_name=media_type)
        deleted_count, _ = model.objects.filter(user=user, import_run=run).delete()
        total_deleted += deleted_count
    music_result = revert_music_import_run(run, user)
    return total_deleted + music_result["deleted"], music_result["reverted"]


def delete_import_schedule(user, task):
    """Remove one of the user's recurring imports; return what was done.

    Last.fm polls every connected account from one shared task, so removing
    it for one user disconnects that user's Last.fm instead. Returns
    "disconnected_lastfm" or "deleted".
    """
    if task.task == LASTFM_POLL_TASK:
        LastFMAccount.objects.filter(user=user).delete()
        return "disconnected_lastfm"
    if not task_belongs_to_user(task, user):
        msg = "Import schedule not found."
        raise DataManagementError(msg)
    if task.task == WATCHLIST_TASK_NAME:
        PlexAccount.objects.filter(user=user).update(watchlist_sync_enabled=False)
    task.delete()
    return "deleted"


def export_schedules_for(user):
    """Return the user's recurring backup exports."""
    return [
        task
        for task in PeriodicTask.objects.filter(task=EXPORT_TASK).select_related(
            "crontab"
        )
        if task_belongs_to_user(task, user)
    ]


def create_export_schedule(
    user,
    *,
    frequency,
    export_time,
    media_types,
    include_lists,
    include_collection,
):
    """Create a recurring backup export and return its PeriodicTask."""
    if frequency not in EXPORT_FREQUENCIES:
        msg = "Invalid export frequency."
        raise DataManagementError(msg)
    if not media_types and not (include_lists or include_collection):
        msg = "Select at least one media type, Custom Lists, or Collection to export."
        raise DataManagementError(msg)
    try:
        parsed_time = dt.datetime.strptime(export_time, "%H:%M").time()  # noqa: DTZ007  # time of day only
    except (TypeError, ValueError) as error:
        msg = "Invalid export time."
        raise DataManagementError(msg) from error

    crontab, _ = CrontabSchedule.objects.get_or_create(
        hour=parsed_time.hour,
        minute=parsed_time.minute,
        day_of_week=EXPORT_FREQUENCIES[frequency],
        timezone=timezone.get_default_timezone(),
    )
    # Several schedules may coexist; only an exact duplicate is refused.
    for schedule in export_schedules_for(user):
        if not schedule.enabled or schedule.crontab_id != crontab.id:
            continue
        existing = json.loads(schedule.kwargs)
        if (
            sorted(existing.get("media_types") or []) == sorted(media_types)
            and existing.get("include_lists") == include_lists
            and existing.get("include_collection") == include_collection
        ):
            msg = "An identical backup schedule already exists."
            raise DataManagementError(msg)

    return PeriodicTask.objects.create(
        name=(
            f"Backup export for {user.username} at {parsed_time} {frequency} "
            f"({uuid.uuid4().hex[:8]})"
        ),
        task=EXPORT_TASK,
        crontab=crontab,
        kwargs=json.dumps(
            {
                "user_id": user.id,
                "media_types": list(media_types),
                "include_lists": include_lists,
                "include_collection": include_collection,
            },
        ),
        start_time=timezone.now(),
        enabled=True,
    )


def delete_export_schedule(user, task):
    """Delete one of the user's backup exports; False if it is not theirs."""
    if task.task != EXPORT_TASK or not task_belongs_to_user(task, user):
        return False
    task.delete()
    return True
