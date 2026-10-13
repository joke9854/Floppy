"""Exact per-item library state for apps that use Floppy as their main tracker.

An item's sync state is every play at its exact instant plus its library status
and score. ``describe_items`` reads it straight from the tracking tables, with
the same rules the watched-state projection uses (``watch_state._derive_*``):

* a movie row contributes its MoviePlay rows when it has any, otherwise its own
  ``end_date`` as one play, and a rewatch may be a second movie row;
* every undropped episode row of a live (unarchived) season is one play.

``refresh_sync_item`` keeps ``SyncItemState`` in step, giving the item a new
per-user sequence whenever that state changes, so the changes feed can list
what moved since a cursor. It runs from the same hooks as the projection.
"""

import hashlib
import json
from collections import defaultdict

from django.apps import apps
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from app.helpers import build_provider_ids
from app.models.choices import MediaTypes, Status

_STATUS_NAMES = {
    Status.PLANNING.value: "planning",
    Status.IN_PROGRESS.value: "in_progress",
    Status.PAUSED.value: "paused",
    Status.DROPPED.value: "dropped",
    Status.COMPLETED.value: "completed",
}
_PENDING_STATUSES = {
    Status.IN_PROGRESS.value,
    Status.PLANNING.value,
    Status.PAUSED.value,
}
SYNCED_MEDIA_TYPES = frozenset(
    {MediaTypes.MOVIE.value, MediaTypes.EPISODE.value, MediaTypes.TV.value},
)
_API_TYPES = {
    MediaTypes.MOVIE.value: "movie",
    MediaTypes.EPISODE.value: "episode",
    MediaTypes.TV.value: "show",
}


def _model(name):
    return apps.get_model(app_label="app", model_name=name)


_ENABLED_ATTR = "_sync_items_enabled"


def is_enabled(user):
    """Return whether this user's items are indexed (a sync connection is on).

    Remembered on the user object, so a bulk write checks once rather than once
    per row; ``forget_enabled`` clears it when the flag changes.
    """
    cached = getattr(user, _ENABLED_ATTR, None)
    if cached is None:
        sequence_model = _model("WatchStateSequence")
        cached = sequence_model.objects.filter(user=user, emit_changes=True).exists()
        setattr(user, _ENABLED_ATTR, cached)
    return cached


def forget_enabled(user):
    """Drop the remembered flag after ``emit_changes`` changed."""
    user.__dict__.pop(_ENABLED_ATTR, None)


def _iso(value):
    return value.isoformat() if value else None


def _play(key, watched_at, client_event_id=None):
    return {
        "key": key,
        "watched_at": _iso(watched_at),
        "client_event_id": client_event_id,
    }


def _preferred_entry(rows):
    """Return the row whose status and score describe the item.

    Pending activity wins over older completed rows, newest first, matching
    ``completion.select_preferred_activity_entry``.
    """
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            0 if row.status in _PENDING_STATUSES else 1,
            -row.created_at.timestamp(),
            -row.pk,
        ),
    )[0]


def _sorted_plays(plays):
    return sorted(plays, key=lambda play: (play["watched_at"] or "", play["key"]))


def _describe(item, *, plays, entry):
    in_library = entry is not None or bool(plays)
    return {
        "type": _API_TYPES[item.media_type],
        "source": item.source,
        "media_id": item.media_id,
        "title": item.title,
        "season_number": item.season_number
        if item.media_type == MediaTypes.EPISODE.value
        else None,
        "episode_number": item.episode_number
        if item.media_type == MediaTypes.EPISODE.value
        else None,
        "ids": build_provider_ids(item),
        "in_library": in_library,
        "status": _STATUS_NAMES.get(entry.status) if entry is not None else None,
        "score": str(entry.score)
        if entry is not None and entry.score is not None
        else None,
        "plays": _sorted_plays(plays),
    }


def describe_items(user, items):
    """Return ``{item_id: state}`` for ``items``, in three queries per type."""
    items = [item for item in items if item.media_type in SYNCED_MEDIA_TYPES]
    by_type = defaultdict(list)
    for item in items:
        by_type[item.media_type].append(item.pk)

    movie_rows = defaultdict(list)
    if by_type[MediaTypes.MOVIE.value]:
        for row in _model("Movie").objects.filter(
            user=user,
            item_id__in=by_type[MediaTypes.MOVIE.value],
        ).prefetch_related("plays"):
            movie_rows[row.item_id].append(row)

    episode_rows = defaultdict(list)
    if by_type[MediaTypes.EPISODE.value]:
        for row in _model("Episode").objects.filter(
            item_id__in=by_type[MediaTypes.EPISODE.value],
            related_season__user=user,
            related_season__order_archived=False,
            dropped=False,
        ):
            episode_rows[row.item_id].append(row)

    show_rows = defaultdict(list)
    if by_type[MediaTypes.TV.value]:
        for row in _model("TV").objects.filter(
            user=user,
            item_id__in=by_type[MediaTypes.TV.value],
        ):
            show_rows[row.item_id].append(row)

    states = {}
    for item in items:
        if item.media_type == MediaTypes.MOVIE.value:
            rows = movie_rows[item.pk]
            plays = []
            for row in rows:
                row_plays = [play for play in row.plays.all() if play.end_date]
                if row_plays:
                    plays.extend(
                        _play(f"movie_play:{play.pk}", play.end_date, play.external_id)
                        for play in row_plays
                    )
                elif row.end_date:
                    plays.append(_play(f"movie:{row.pk}", row.end_date))
            states[item.pk] = _describe(item, plays=plays, entry=_preferred_entry(rows))
        elif item.media_type == MediaTypes.EPISODE.value:
            plays = [
                _play(
                    f"episode:{row.pk}",
                    row.end_date,
                    str(row.watch_operation_id) if row.watch_operation_id else None,
                )
                for row in episode_rows[item.pk]
            ]
            states[item.pk] = _describe(item, plays=plays, entry=None)
        else:
            states[item.pk] = _describe(
                item,
                plays=[],
                entry=_preferred_entry(show_rows[item.pk]),
            )
    return states


def _digest(state):
    return hashlib.sha256(
        json.dumps(state, sort_keys=True, default=str).encode("utf-8"),
    ).hexdigest()


def _allocate_sequences(user, count):
    """Reserve ``count`` consecutive sequences; return the first one."""
    # One UPDATE both increments and row-locks the counter until commit.
    sequence_model = _model("SyncItemSequence")
    rows = sequence_model.objects.filter(user=user)
    if not rows.update(last_sequence=F("last_sequence") + count):
        sequence_model.objects.get_or_create(user=user)
        rows.update(last_sequence=F("last_sequence") + count)
    return rows.values_list("last_sequence", flat=True).get() - count + 1


def head_sequence(user):
    """Return the newest sequence handed out for this user (0 when none)."""
    row = _model("SyncItemSequence").objects.filter(user=user).first()
    return row.last_sequence if row else 0


def refresh_sync_item(user, item):
    """Re-index one item; give it a new sequence when its state changed.

    An item that was never indexed and has nothing to report stays out of the
    index, so untracked items cost nothing. Once indexed, an item that loses its
    last play and library entry is re-sequenced with ``in_library: false``: that
    is how an app learns about a removal.
    """
    if item is None:
        return
    refresh_sync_items(user, [item])


_REFRESH_CHUNK = 200


def refresh_sync_items(user, items):
    """Re-index many items with a fixed number of queries per chunk.

    Bulk writes (bootstrap batches, ``bulk_update``) fire no signals; they call
    this once with everything they touched instead of once per row.
    """
    if user is None or not is_enabled(user):
        return
    unique = {}
    for item in items:
        if item is not None and item.media_type in SYNCED_MEDIA_TYPES:
            unique.setdefault(item.pk, item)
    pending = list(unique.values())
    for start in range(0, len(pending), _REFRESH_CHUNK):
        _refresh_chunk(user, pending[start : start + _REFRESH_CHUNK])


def _refresh_chunk(user, items):
    states = describe_items(user, items)
    digests = {pk: _digest(state) for pk, state in states.items()}
    state_model = _model("SyncItemState")
    # No savepoint: a failed index write must fail the caller's write too.
    with transaction.atomic(savepoint=False):
        existing = {
            row.item_id: row
            for row in state_model.objects.filter(user=user, item_id__in=list(states))
        }
        changed = [
            item
            for item in items
            if (
                existing[item.pk].digest != digests[item.pk]
                if item.pk in existing
                else states[item.pk]["in_library"]
            )
        ]
        if not changed:
            return
        sequence = _allocate_sequences(user, len(changed))
        created, updated = [], []
        now = timezone.now()
        for offset, item in enumerate(changed):
            row = existing.get(item.pk)
            if row is None:
                created.append(
                    state_model(
                        user=user,
                        item=item,
                        sequence=sequence + offset,
                        digest=digests[item.pk],
                    ),
                )
            else:
                row.sequence = sequence + offset
                row.digest = digests[item.pk]
                row.updated_at = now  # bulk_update skips auto_now
                updated.append(row)
        if created:
            state_model.objects.bulk_create(created)
        if updated:
            state_model.objects.bulk_update(
                updated,
                fields=["sequence", "digest", "updated_at"],
            )


def library_item_ids(user):
    """Return the ids of every movie, episode and show the user tracks."""
    ids = set(
        _model("Movie").objects.filter(user=user).values_list("item_id", flat=True),
    )
    ids.update(
        _model("TV").objects.filter(user=user).values_list("item_id", flat=True),
    )
    ids.update(
        _model("Episode")
        .objects.filter(
            related_season__user=user,
            related_season__order_archived=False,
            dropped=False,
            item__isnull=False,
        )
        .values_list("item_id", flat=True),
    )
    return ids
