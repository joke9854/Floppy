"""Library actions shared by the web views and the API (P1-D).

Each function does the whole change, side effects included (cache keys,
media-list caches), so the web view and the API view cannot drift apart.
Validation that needs a provider (language codes, MusicBrainz releases)
stays with the caller, which decides how to answer a provider failure.
"""

from django.core.cache import cache
from django.db import transaction

from app import cache_utils
from app.models import (
    CollectionEntry,
    HardcoverEditionPreference,
    Item,
    ItemTag,
    MediaTypes,
    MetadataProviderPreference,
    Sources,
)
from app.services import metadata_resolution


def set_hardcover_edition(user, item, edition_id):
    """Use `edition_id` for this Hardcover book for `user`."""
    HardcoverEditionPreference.objects.update_or_create(
        user=user,
        item=item,
        defaults={"edition_id": edition_id},
    )
    cache.delete(f"{Sources.HARDCOVER.value}_{MediaTypes.BOOK.value}_{item.media_id}")
    cache.delete(
        f"{Sources.HARDCOVER.value}_{MediaTypes.BOOK.value}_{item.media_id}_{edition_id}",
    )


def set_metadata_language(user, item, language):
    """Show `item` in `language` for `user`; "" means the server default."""
    MetadataProviderPreference.objects.update_or_create(
        user=user,
        item=item,
        defaults={"language": language},
    )


def remap_metadata_provider(user, item, media_type, provider, provider_media_id):
    """Link `item` to `provider_media_id` on `provider` and prefer that provider.

    The link is stored on the item, so it applies to every user; the
    provider preference is `user`'s own.
    """
    metadata_resolution.upsert_provider_links(
        item,
        {"media_id": provider_media_id},
        provider=provider,
        provider_media_type=metadata_resolution.provider_route_media_type(
            media_type,
            provider,
        ),
    )
    MetadataProviderPreference.objects.update_or_create(
        user=user,
        item=item,
        defaults={"provider": provider},
    )


def toggle_tag(user, tag, action, item_ids):
    """Add (`action="add"`) or remove `tag` on the items; return the item ids used.

    Ids of items that do not exist are ignored.
    """
    existing_ids = sorted(
        Item.objects.filter(id__in=item_ids).values_list("id", flat=True),
    )
    if action == "add":
        ItemTag.objects.bulk_create(
            [ItemTag(tag=tag, item_id=item_id) for item_id in existing_ids],
            ignore_conflicts=True,
        )
    else:
        ItemTag.objects.filter(tag=tag, item_id__in=existing_ids).delete()
    cache_utils.clear_media_list_cache_for_user(user.id)
    return existing_ids


def add_items_to_collection(user, item_ids):
    """Add the items to `user`'s collection; shows and seasons add their episodes.

    Returns counts plus the ids that were skipped (unknown items, or a show or
    season whose episodes could not be expanded).
    """
    from app.collection_views import (
        _SEASON_OR_SHOW_MEDIA_TYPES,
        _expand_collection_entry_to_episodes,
    )

    items_by_id = Item.objects.in_bulk(item_ids)
    result = {"created": 0, "already_present": 0, "skipped_ids": []}
    result["skipped_ids"] = [
        item_id for item_id in item_ids if item_id not in items_by_id
    ]

    ordinary_items = [
        item
        for item_id, item in items_by_id.items()
        if item_id in item_ids and item.media_type not in _SEASON_OR_SHOW_MEDIA_TYPES
    ]
    existing_ids = set(
        CollectionEntry.objects.filter(
            user=user,
            item_id__in=[item.id for item in ordinary_items],
        ).values_list("item_id", flat=True),
    )
    to_create = [
        CollectionEntry(user=user, item=item)
        for item in ordinary_items
        if item.id not in existing_ids
    ]
    if to_create:
        CollectionEntry.objects.bulk_create(to_create)
    result["created"] += len(to_create)
    result["already_present"] += len(ordinary_items) - len(to_create)

    for item_id in item_ids:
        item = items_by_id.get(item_id)
        if item is None or item.media_type not in _SEASON_OR_SHOW_MEDIA_TYPES:
            continue
        try:
            with transaction.atomic():
                created_entries, skipped_count = _expand_collection_entry_to_episodes(
                    user,
                    item,
                    cleaned_data={},
                )
        except Exception:
            result["skipped_ids"].append(item_id)
            continue
        result["created"] += len(created_entries)
        result["already_present"] += skipped_count

    return result
