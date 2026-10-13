"""Per-item sync index: what an app needs to mirror a user's library exactly.

``WatchState`` summarises an item (watched, play count, last play). An app that
uses Floppy as its main tracker needs more: every play at its exact instant, and
the library status and score. ``SyncItemState`` keeps a digest of exactly that
per (user, item) and gives the item a new per-user sequence whenever it changes,
so ``/api/v1/sync/items/changes/`` can list what moved since a cursor.

Like the watched-state log, it is only maintained for users with a
synchronizing connection (``WatchStateSequence.emit_changes``); everything from
before that is covered by the snapshot endpoint, which reads the library
directly.
"""

from django.conf import settings
from django.db import models


class SyncItemState(models.Model):
    """The last digest and sequence of one item's plays, status and score."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sync_item_states",
    )
    item = models.ForeignKey(
        "app.Item",
        on_delete=models.CASCADE,
        related_name="sync_item_states",
    )
    sequence = models.BigIntegerField()
    digest = models.CharField(max_length=64)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        """Meta options for the model."""

        constraints = [
            models.UniqueConstraint(
                fields=["user", "item"],
                name="app_syncitemstate_unique_user_item",
            ),
        ]
        indexes = [
            models.Index(
                fields=["user", "sequence"],
                name="app_syncitemstate_user_seq",
            ),
        ]

    def __str__(self):
        """Return the user, item and sequence."""
        return f"{self.user_id}:{self.item_id}@{self.sequence}"


class SyncItemSequence(models.Model):
    """Per-user allocator for ``SyncItemState.sequence``."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sync_item_sequence",
    )
    last_sequence = models.BigIntegerField(default=0)

    def __str__(self):
        """Return the user and the last sequence handed out."""
        return f"{self.user_id}@{self.last_sequence}"
