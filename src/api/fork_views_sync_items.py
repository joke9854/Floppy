# FORK: read side for apps that use Floppy as their main tracker. A full
# snapshot for the first sync, then a changes feed after a cursor; both return
# every play at its exact instant plus library status and score per item.
from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import Item, SyncItemState
from app.services import sync_items

from .contract_serializers import DetailErrorSerializer

DEFAULT_LIMIT = 200
MAX_LIMIT = 500


class SyncPlaySerializer(serializers.Serializer):
    """One play of an item."""

    key = serializers.CharField(
        help_text="Floppy's id for the play. It can change when Floppy "
        "reorganises storage; match plays by watched_at.",
    )
    watched_at = serializers.DateTimeField(
        allow_null=True,
        help_text="The exact instant, to the microsecond as stored.",
    )
    client_event_id = serializers.CharField(
        allow_null=True,
        help_text="The id the app sent when it recorded the play, when known.",
    )


class SyncItemSerializer(serializers.Serializer):
    """The whole sync state of one movie, episode or show."""

    sequence = serializers.IntegerField(
        required=False,
        help_text="Only in the changes feed.",
    )
    type = serializers.ChoiceField(choices=("movie", "episode", "show"))
    source = serializers.CharField()
    media_id = serializers.CharField(help_text="For an episode, its show's id.")
    season_number = serializers.IntegerField(allow_null=True)
    episode_number = serializers.IntegerField(allow_null=True)
    ids = serializers.DictField(child=serializers.CharField())
    in_library = serializers.BooleanField(
        help_text="False once the item has no plays and no library entry left: "
        "the app should remove it.",
    )
    status = serializers.ChoiceField(
        choices=("planning", "in_progress", "paused", "dropped", "completed"),
        allow_null=True,
        help_text="Movies and shows; null for episodes.",
    )
    score = serializers.CharField(allow_null=True)
    plays = SyncPlaySerializer(many=True, help_text="Every play, oldest first.")


class SyncItemsSnapshotSerializer(serializers.Serializer):
    """One page of the full snapshot."""

    results = SyncItemSerializer(many=True)
    next_after = serializers.IntegerField(
        allow_null=True,
        help_text="Pass as 'after' for the next page; null on the last page.",
    )
    cursor = serializers.IntegerField(
        help_text="The changes-feed position when this page was read. Keep "
        "the value from the first page and follow the feed from it.",
    )


class SyncItemsChangesSerializer(serializers.Serializer):
    """Items that changed after a cursor, in order."""

    results = SyncItemSerializer(many=True)
    cursor = serializers.IntegerField(help_text="Pass as 'cursor' next time.")
    has_more = serializers.BooleanField()


def _limit(request):
    try:
        value = int(request.query_params.get("limit", DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return None
    return value if 1 <= value <= MAX_LIMIT else None


def _non_negative(request, name):
    raw = request.query_params.get(name, "0")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def _bad(detail):
    return Response({"detail": detail}, status=HTTP.BAD_REQUEST)


# /api/v1/sync/items/snapshot/
class SyncItemsSnapshotView(drf_views.APIView):
    """Every movie, episode and show in the library, page by page."""

    @extend_schema(
        description=(
            "The full sync state of the library, ordered by Floppy's item id. "
            "Start without 'after', then pass 'next_after' until it is null. "
            "Keep 'cursor' from the first page and then follow "
            "/sync/items/changes/ from it, so nothing that changes while "
            "paging is missed. Needs an active app sync connection "
            "(POST /sync/connections/) for the changes feed to be kept."
        ),
        parameters=[
            OpenApiParameter("after", int, description="Item id to continue after."),
            OpenApiParameter("limit", int, description=f"1-{MAX_LIMIT}, default {DEFAULT_LIMIT}."),
        ],
        responses={200: SyncItemsSnapshotSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request):
        """Return one page of the snapshot."""
        limit = _limit(request)
        after = _non_negative(request, "after")
        if limit is None:
            return _bad(f"'limit' must be from 1 to {MAX_LIMIT}.")
        if after is None:
            return _bad("'after' must be a non-negative integer.")

        cursor = sync_items.head_sequence(request.user)
        ids = sorted(
            item_id
            for item_id in sync_items.library_item_ids(request.user)
            if item_id > after
        )
        page_ids = ids[:limit]
        items = Item.objects.filter(pk__in=page_ids).order_by("pk")
        states = sync_items.describe_items(request.user, list(items))
        results = [states[item_id] for item_id in page_ids if item_id in states]
        return Response(
            {
                "results": results,
                "next_after": page_ids[-1] if len(ids) > limit else None,
                "cursor": cursor,
            },
            status=HTTP.OK,
        )


# /api/v1/sync/items/changes/
class SyncItemsChangesView(drf_views.APIView):
    """Items whose plays, status or score changed after a cursor."""

    @extend_schema(
        description=(
            "Items that changed after 'cursor', oldest change first, each with "
            "its whole current state. An item that changed several times "
            "appears once, at its latest position. 'in_library: false' means "
            "it was removed. Changes are recorded while the account has an "
            "active app sync connection; start from a snapshot's cursor."
        ),
        parameters=[
            OpenApiParameter("cursor", int, description="Last cursor seen; 0 for all."),
            OpenApiParameter("limit", int, description=f"1-{MAX_LIMIT}, default {DEFAULT_LIMIT}."),
        ],
        responses={200: SyncItemsChangesSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request):
        """Return the next page of changes."""
        limit = _limit(request)
        cursor = _non_negative(request, "cursor")
        if limit is None:
            return _bad(f"'limit' must be from 1 to {MAX_LIMIT}.")
        if cursor is None:
            return _bad("'cursor' must be a non-negative integer.")

        rows = list(
            SyncItemState.objects.filter(user=request.user, sequence__gt=cursor)
            .select_related("item")
            .order_by("sequence")[: limit + 1],
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        states = sync_items.describe_items(request.user, [row.item for row in rows])
        results = [
            {"sequence": row.sequence, **states[row.item_id]}
            for row in rows
            if row.item_id in states
        ]
        return Response(
            {
                "results": results,
                "cursor": rows[-1].sequence if rows else cursor,
                "has_more": has_more,
            },
            status=HTTP.OK,
        )
