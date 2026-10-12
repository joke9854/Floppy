"""Coarse "something changed here" timestamps for pull clients.

A client that polls every feed on every sync spends most of its requests
learning nothing moved. These timestamps let it ask once and fetch only the
areas that did. They are advisory: a bump with no visible change costs the
client one extra fetch, while a missed bump would hide a change, so call sites
err toward bumping.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db import IntegrityError, transaction
from django.utils import timezone

from app.models.watch_state import SyncActivity, SyncActivityCategory

CATEGORIES = tuple(category.value for category in SyncActivityCategory)

# While a batch is open, touches are collected here instead of written.
_PENDING = ContextVar("sync_activity_pending", default=None)


@contextmanager
def batched_activity():
    """Collapse the touches made inside into one write per user and category.

    A request that creates hundreds of rows would otherwise stamp the same
    category once per row. The stamp is written once on the way out, so it still
    lands after the data it describes. Usable as a decorator.
    """
    if _PENDING.get() is not None:
        # Nested: the outermost batch flushes.
        yield
        return

    pending = {}
    token = _PENDING.set(pending)
    try:
        yield
    finally:
        _PENDING.reset(token)
        for user_id, categories in pending.items():
            touch_activity(user_id, *categories)


def touch_activity(user, *categories):
    """Record that these areas of ``user``'s data changed just now.

    Costs one UPDATE per category; a row is only inserted the first time a
    category is used. The insert runs in its own savepoint so losing a race to
    create the row cannot poison the caller's transaction.
    """
    user_id = getattr(user, "pk", user)
    if user_id is None:
        return

    for category in categories:
        if category not in CATEGORIES:
            msg = f"Unknown sync activity category: {category}"
            raise ValueError(msg)

    pending = _PENDING.get()
    if pending is not None:
        pending.setdefault(user_id, {}).update(dict.fromkeys(categories))
        return

    now = timezone.now()
    for category in dict.fromkeys(categories):
        updated = SyncActivity.objects.filter(
            user_id=user_id,
            category=category,
        ).update(changed_at=now)
        if updated:
            continue

        try:
            with transaction.atomic():
                SyncActivity.objects.create(
                    user_id=user_id,
                    category=category,
                    changed_at=now,
                )
        except IntegrityError:
            SyncActivity.objects.filter(user_id=user_id, category=category).update(
                changed_at=now,
            )


def activity_snapshot(user):
    """Return ``{category: datetime | None, "all": datetime | None}``."""
    snapshot = dict.fromkeys(CATEGORIES)
    snapshot.update(
        SyncActivity.objects.filter(user=user).values_list("category", "changed_at"),
    )
    seen = [value for value in snapshot.values() if value is not None]
    snapshot["all"] = max(seen) if seen else None
    return snapshot
