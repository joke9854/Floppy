"""History-aware bulk writes that keep the sync surfaces in step.

``bulk_create_with_history`` and ``bulk_update_with_history`` bypass Django's
save signals, so the watch-state projection and the sync activity stamps never
hear about rows written through them. These wrappers keep the originals'
signatures and return values and do that bookkeeping once per call.
"""

from simple_history.utils import (
    bulk_create_with_history as _bulk_create_with_history,
)
from simple_history.utils import (
    bulk_update_with_history as _bulk_update_with_history,
)

from app.services.sync_activity import touch_activity
from app.services.watch_state import project_watch_state_for_change


def _owner(obj):
    """Return the user a tracking row belongs to, or None."""
    user = getattr(obj, "user", None)
    if user is not None:
        return user
    season = getattr(obj, "related_season", None)
    return getattr(season, "user", None)


def _record_bulk_write(objs, model):
    """Stamp the library as changed and project any episodes written.

    Projection is the same recompute the Episode save signal runs, once per
    distinct (user, item): a retried or rewatched item is still one recompute
    because the projection reads the stores, not the rows passed in. It honours
    ``suspend_projection`` through ``project_watch_state_for_change``.
    """
    owners = {}
    projected = set()
    for obj in objs:
        user = _owner(obj)
        if user is None:
            continue
        owners[user.pk] = user
        if model._meta.label == "app.Episode" and obj.item_id is not None:
            key = (user.pk, obj.item_id)
            if key not in projected:
                projected.add(key)
                project_watch_state_for_change(user, obj.item)

    for user_id in owners:
        touch_activity(user_id, "library")


def bulk_create_with_history(objs, model, *args, **kwargs):
    """Create rows with history, then project watch state and stamp activity."""
    objs = list(objs)
    created = _bulk_create_with_history(objs, model, *args, **kwargs)
    _record_bulk_write(objs, model)
    return created


def bulk_update_with_history(objs, model, *args, **kwargs):
    """Update rows with history, then project watch state and stamp activity."""
    objs = list(objs)
    updated = _bulk_update_with_history(objs, model, *args, **kwargs)
    _record_bulk_write(objs, model)
    return updated
