"""Screen preferences that are not plain fields of user/preferences (P1-F).

Table columns are stored per media type and table, and which columns exist
depends on the sort, so they get their own endpoint. Converting the anime
library is a background action, not a preference.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.columns import media_column_sort, resolve_column_config, sanitize_column_prefs
from app.models import MediaTypes
from users.models import ListDetailSortChoices, MediaSortChoices

from .contract_serializers import DetailErrorSerializer, TaskQueuedSerializer

TABLE_TYPES = ("media", "artist", "album", "list")
MUSIC_TABLE_TYPES = ("artist", "album")
ALL_MEDIA = "all"


class TableColumnSerializer(serializers.Serializer):
    """One column the user can show, hide or move."""

    key = serializers.CharField()
    label = serializers.CharField()
    visible = serializers.BooleanField()


class TableColumnsSerializer(serializers.Serializer):
    """The user's columns for one table, in display order."""

    table_type = serializers.CharField()
    media_type = serializers.CharField()
    sort = serializers.CharField(help_text="The sort the column rules used.")
    columns = TableColumnSerializer(many=True)


class TableColumnsRequestSerializer(serializers.Serializer):
    """New order and hidden columns; unknown keys are dropped."""

    table_type = serializers.ChoiceField(choices=TABLE_TYPES, required=False)
    media_type = serializers.CharField()
    sort = serializers.CharField(required=False)
    order = serializers.ListField(child=serializers.CharField())
    hidden = serializers.ListField(child=serializers.CharField())


_TABLE_PARAMETERS = [
    OpenApiParameter(
        "table_type",
        OpenApiTypes.STR,
        enum=list(TABLE_TYPES),
        description=(
            "`media` (default) for a library list, `artist` or `album` for the "
            "music tables, `list` for a custom list's table."
        ),
    ),
    OpenApiParameter(
        "media_type",
        OpenApiTypes.STR,
        required=True,
        description="Media type; `all` is accepted for `list` tables.",
    ),
    OpenApiParameter(
        "sort",
        OpenApiTypes.STR,
        description=(
            "Sort shown with the table; some columns exist only for some sorts. "
            "Defaults to the saved sort (`date_added` for lists)."
        ),
    ),
]


def _table_target(user, data):
    """Return ((table_type, media_type, sort), None) or (None, error Response)."""

    def bad(detail):
        return None, Response({"detail": detail}, status=HTTP.BAD_REQUEST)

    table_type = str(data.get("table_type") or "media")
    media_type = str(data.get("media_type") or "")
    sort = str(data.get("sort") or "")
    if table_type not in TABLE_TYPES:
        return bad(f"table_type must be one of {', '.join(TABLE_TYPES)}.")
    if table_type == "list":
        if media_type != ALL_MEDIA and media_type not in MediaTypes.values:
            return bad("Unknown media_type.")
        sort = sort or ListDetailSortChoices.DATE_ADDED
        if sort not in ListDetailSortChoices.values:
            return bad("Unknown sort for a list table.")
        return (table_type, media_type, sort), None
    if media_type not in MediaTypes.values:
        return bad("Unknown media_type.")
    if table_type in MUSIC_TABLE_TYPES and media_type != MediaTypes.MUSIC.value:
        return bad("artist and album tables exist only for music.")
    sort = sort or getattr(user, f"{media_type}_sort", MediaSortChoices.SCORE)
    if sort not in MediaSortChoices.values:
        return bad("Unknown sort.")
    return (table_type, media_type, media_column_sort(media_type, sort)), None


def _columns_payload(user, table_type, media_type, sort):
    return {
        "table_type": table_type,
        "media_type": media_type,
        "sort": sort,
        "columns": resolve_column_config(media_type, sort, user, table_type),
    }


class TableColumnsView(drf_views.APIView):
    """Read or save the column order and visibility of a table."""

    @extend_schema(
        operation_id="getTableColumns",
        parameters=_TABLE_PARAMETERS,
        responses={200: TableColumnsSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request):
        """Return the user's columns for the table."""
        target, error = _table_target(request.user, request.query_params)
        if error:
            return error
        return Response(_columns_payload(request.user, *target), status=HTTP.OK)

    @extend_schema(
        operation_id="setTableColumns",
        request=TableColumnsRequestSerializer,
        responses={
            200: TableColumnsSerializer,
            400: DetailErrorSerializer,
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="Demo accounts are view-only.",
            ),
        },
    )
    def put(self, request):
        """Save the order and hidden columns, then return the result."""
        if request.user.is_demo:
            return Response(
                {"detail": "This section is view-only for demo accounts."},
                status=HTTP.FORBIDDEN,
            )
        data = request.data if isinstance(request.data, dict) else {}
        target, error = _table_target(request.user, data)
        if error:
            return error
        order = data.get("order")
        hidden = data.get("hidden")
        if not all(
            isinstance(values, list) and all(isinstance(v, str) for v in values)
            for values in (order, hidden)
        ):
            return Response(
                {"detail": "order and hidden must be lists of column keys."},
                status=HTTP.BAD_REQUEST,
            )
        table_type, media_type, sort = target
        clean_order, clean_hidden = sanitize_column_prefs(
            media_type=media_type,
            current_sort=sort,
            user=request.user,
            table_type=table_type,
            order=order,
            hidden=hidden,
        )
        request.user.update_column_prefs(
            media_type=media_type,
            table_type=table_type,
            order=clean_order,
            hidden=clean_hidden,
        )
        return Response(_columns_payload(request.user, *target), status=HTTP.OK)


class AnimeLibraryConvertView(drf_views.APIView):
    """Convert the user's tracked anime to their `anime_library_mode`.

    Runs in the background; titles that cannot be converted safely are left
    as they are.
    """

    @extend_schema(
        operation_id="convertAnimeLibrary",
        request=None,
        responses={
            202: TaskQueuedSerializer,
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="Demo accounts are view-only.",
            ),
        },
    )
    def post(self, request):
        """Queue the conversion and return its task id."""
        from app.tasks_anime_library_repair import convert_anime_library_shape_task

        if request.user.is_demo:
            return Response(
                {"detail": "This section is view-only for demo accounts."},
                status=HTTP.FORBIDDEN,
            )
        task = convert_anime_library_shape_task.delay(request.user.id)
        return Response({"task_id": task.id}, status=HTTP.ACCEPTED)
