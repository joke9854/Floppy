"""List changes shared by the web views and the API (P1-E)."""

import contextlib
from dataclasses import dataclass

from django.db import transaction

from app.models import Item, MediaTypes, Status
from app.templatetags.app_tags import media_type_readable_plural
from lists import smart_rules
from lists import tasks as list_tasks
from lists.models import CustomList, CustomListItem, ListActivity, ListActivityType
from users.models import MediaSortChoices


def _share_view_name(media_type, normalized_rules):
    """Build a short, human-readable name for a Share View smart list."""
    parts = [media_type_readable_plural(media_type)]

    statuses = normalized_rules.get("status") or []
    if statuses:
        parts.append(", ".join(Status(value).label for value in statuses))

    sort_value = normalized_rules.get("sort")
    if sort_value:
        with contextlib.suppress(ValueError):
            parts.append(f"sorted by {MediaSortChoices(sort_value).label}")

    return " — ".join(parts)


def share_view(user, media_type, payload):
    """Create, or reuse, the user's public smart list for this view.

    `payload` holds the view's filters in the smart-rules shape (a QueryDict
    or a dict). Returns (custom_list, created). Raises ValueError for an
    unknown media type.
    """
    if media_type not in MediaTypes.values:
        msg = "Invalid media type"
        raise ValueError(msg)

    normalized = smart_rules.normalize_rule_payload(payload, user)
    smart_media_types = [media_type]
    smart_filters = {
        key: normalized.get(key, smart_rules.SMART_FILTER_DEFAULTS[key])
        for key in smart_rules.SMART_FILTER_KEYS
    }

    existing = CustomList.objects.filter(
        owner=user,
        is_smart=True,
        visibility="public",
        smart_media_types=smart_media_types,
        smart_filters=smart_filters,
    ).first()
    if existing:
        return existing, False

    custom_list = CustomList.objects.create(
        name=_share_view_name(media_type, normalized),
        owner=user,
        visibility="public",
        is_smart=True,
        smart_media_types=smart_media_types,
        smart_filters=smart_filters,
    )
    ListActivity.objects.create(
        custom_list=custom_list,
        user=user,
        activity_type=ListActivityType.LIST_CREATED,
    )
    list_tasks.sync_smart_list_task.delay(custom_list.id)
    return custom_list, True


@dataclass(frozen=True)
class BulkAddResult:
    """Counts from adding many items to a list."""

    added: int
    already_present: int
    skipped: int


def add_items_to_list(user, custom_list, item_ids):
    """Add the items to a manual list the user may edit.

    Unknown item ids are skipped and items already on the list are left as
    they are. The caller checks edit permission and that the list is not
    smart.
    """
    items_by_id = Item.objects.in_bulk(item_ids)
    skipped = len(item_ids) - len(items_by_id)
    with transaction.atomic():
        CustomListItem.objects.lock_custom_lists([custom_list.id])
        existing_ids = set(
            CustomListItem.objects.filter(
                custom_list=custom_list,
                item_id__in=items_by_id,
            ).values_list("item_id", flat=True),
        )
        added_items = [
            item for item_id, item in items_by_id.items() if item_id not in existing_ids
        ]
        CustomListItem.objects.bulk_create(
            [
                CustomListItem(custom_list=custom_list, item=item, added_by=user)
                for item in added_items
            ],
        )
        ListActivity.objects.bulk_create(
            [
                ListActivity(
                    custom_list=custom_list,
                    user=user,
                    activity_type=ListActivityType.ITEM_ADDED,
                    item=item,
                )
                for item in added_items
            ],
        )
    return BulkAddResult(
        added=len(added_items),
        already_present=len(items_by_id) - len(added_items),
        skipped=skipped,
    )
