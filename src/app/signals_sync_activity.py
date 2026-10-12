"""Bump the sync activity timestamps when the data behind them changes.

Same approach as ``signals_watch_state``: every write path ends in a save or
delete on one of these models, so hooking them here covers the UI, the API, the
webhooks and the importers without editing any of them. Watched-state bumps live
with the projection itself, and bulk paths bump explicitly because
``bulk_create`` and ``bulk_update`` fire no signals.
"""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import QuerySet
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from app.models import CollectionEntry, Media, PlaybackProgress, Podcast
from app.services.sync_activity import touch_activity


def _user_is_being_deleted(origin):
    """Return whether this deletion cascades from removing the user itself.

    The user's activity rows are deleted by the same cascade, so recording a
    fresh one for a user who is going away would leave a dangling reference.
    """
    user_model = get_user_model()
    if isinstance(origin, user_model):
        return True
    return isinstance(origin, QuerySet) and issubclass(origin.model, user_model)


def _touch(user_getter, *categories, origin=None):
    """Touch categories for the row's user, unless there is nobody to tell."""
    if origin is not None and _user_is_being_deleted(origin):
        return
    try:
        user_id = user_getter()
    except ObjectDoesNotExist:
        return
    touch_activity(user_id, *categories)


def _on_media_saved(sender, instance, **kwargs):
    """Stamp the library when a tracking row (status, score, notes...) is saved."""
    if sender is Podcast:
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "played_up_to_seconds" in update_fields:
            _touch(lambda: instance.user_id, "library", "playback")
            return
    _touch(lambda: instance.user_id, "library")


def _on_media_deleted(sender, instance, **kwargs):
    """Stamp the library and removals when a tracking row is deleted."""
    _touch(
        lambda: instance.user_id,
        "library",
        "removed",
        origin=kwargs.get("origin"),
    )


def connect_media_receivers():
    """Connect to every concrete ``Media`` subclass, TV and Season included."""
    for model in apps.get_models():
        if issubclass(model, Media):
            post_save.connect(
                _on_media_saved,
                sender=model,
                dispatch_uid=f"sync_activity_save_{model._meta.label}",
            )
            post_delete.connect(
                _on_media_deleted,
                sender=model,
                dispatch_uid=f"sync_activity_delete_{model._meta.label}",
            )


connect_media_receivers()


@receiver(post_save, sender=PlaybackProgress)
def touch_playback_on_save(sender, instance, **kwargs):
    """Stamp playback when a resume position is written."""
    _touch(lambda: instance.user_id, "playback")


@receiver(post_delete, sender=PlaybackProgress)
def touch_playback_on_delete(sender, instance, **kwargs):
    """Stamp playback when a resume position is cleared."""
    _touch(lambda: instance.user_id, "playback", origin=kwargs.get("origin"))


@receiver(post_save, sender=CollectionEntry)
def touch_collection_on_save(sender, instance, **kwargs):
    """Stamp the collection when an entry is added or edited."""
    _touch(lambda: instance.user_id, "collection")


@receiver(post_delete, sender=CollectionEntry)
def touch_collection_on_delete(sender, instance, **kwargs):
    """Stamp the collection and removals when an entry is deleted."""
    _touch(
        lambda: instance.user_id,
        "collection",
        "removed",
        origin=kwargs.get("origin"),
    )


@receiver(post_save, sender="lists.CustomList")
def touch_lists_on_list_save(sender, instance, **kwargs):
    """Stamp lists when a list is created or edited."""
    _touch(lambda: instance.owner_id, "lists")


@receiver(post_delete, sender="lists.CustomList")
def touch_lists_on_list_delete(sender, instance, **kwargs):
    """Stamp lists and removals when a list is deleted."""
    _touch(
        lambda: instance.owner_id,
        "lists",
        "removed",
        origin=kwargs.get("origin"),
    )


@receiver(post_save, sender="lists.CustomListItem")
def touch_lists_on_item_save(sender, instance, **kwargs):
    """Stamp lists when an item is added to or changed in a list."""
    _touch(lambda: instance.custom_list.owner_id, "lists")


@receiver(post_delete, sender="lists.CustomListItem")
def touch_lists_on_item_delete(sender, instance, **kwargs):
    """Stamp lists and removals when an item is removed from a list.

    When the whole list is going away the list's own receiver already covered
    it, and its row may no longer be readable here.
    """
    _touch(
        lambda: instance.custom_list.owner_id,
        "lists",
        "removed",
        origin=kwargs.get("origin"),
    )
