"""List actions the web had and the API lacked (P1-E).

Share the current library view as a public smart list, add many items to
a list, and export or import one list as CSV. The share and bulk-add
changes live in `lists.list_actions`, shared with the web views.
"""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from django.http import StreamingHttpResponse
from django.utils.text import slugify
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from integrations import exports
from integrations.upload_staging import enqueue_staged_task, stage_uploaded_file
from lists import list_actions
from lists import tasks as list_tasks
from lists.models import CustomList

from .contract_serializers import DetailErrorSerializer, TaskQueuedSerializer
from .fork_views_library import MAX_BULK_ITEMS, _bulk_item_ids
from .fork_views_lists import _get_editable_list

logger = logging.getLogger(__name__)


# --- /api/v1/lists/share-view/ ----------------------------------------------


class ListShareViewRequestSerializer(serializers.Serializer):
    """The library view to share, in the smart-rules shape.

    Besides `media_type`, any smart filter key (status, rating, genre, year,
    sort, ...) is accepted; omitted filters use their defaults.
    """

    media_type = serializers.CharField()


class ListShareViewSerializer(serializers.Serializer):
    """The public smart list holding the shared view."""

    list_id = serializers.IntegerField()
    url = serializers.CharField(help_text="Public web path of the list.")
    created = serializers.BooleanField(
        help_text="False when an identical shared view already existed.",
    )


class ListShareViewView(drf_views.APIView):
    """Share a filtered library view as a public smart list.

    Sharing the same view again returns the existing list.
    """

    @extend_schema(
        operation_id="shareLibraryView",
        request=ListShareViewRequestSerializer,
        responses={
            200: ListShareViewSerializer,
            201: ListShareViewSerializer,
            400: DetailErrorSerializer,
        },
    )
    def post(self, request):
        """Create or reuse the list and return it."""
        data = request.data if isinstance(request.data, dict) else {}
        try:
            custom_list, created = list_actions.share_view(
                request.user,
                str(data.get("media_type") or ""),
                data,
            )
        except ValueError:
            return Response({"detail": "Invalid media type."}, status=HTTP.BAD_REQUEST)
        return Response(
            {
                "list_id": custom_list.id,
                "url": custom_list.get_absolute_url(),
                "created": created,
            },
            status=HTTP.CREATED if created else HTTP.OK,
        )


# --- /api/v1/lists/{list_id}/items/bulk/ ------------------------------------


class ListBulkAddRequestSerializer(serializers.Serializer):
    """Items to add."""

    item_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        help_text=f"Floppy item ids, at most {MAX_BULK_ITEMS}.",
    )


class ListBulkAddSerializer(serializers.Serializer):
    """What happened to the requested items."""

    added = serializers.IntegerField()
    already_present = serializers.IntegerField()
    skipped = serializers.IntegerField(help_text="Ids that match no item.")


class ListBulkAddView(drf_views.APIView):
    """Add many items to a manual list the user owns or collaborates on."""

    @extend_schema(
        operation_id="addListItemsBulk",
        request=ListBulkAddRequestSerializer,
        responses={
            200: ListBulkAddSerializer,
            400: DetailErrorSerializer,
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="No permission to edit, or the list is a smart list.",
            ),
            404: DetailErrorSerializer,
        },
    )
    def post(self, request, list_id):
        """Add the items and return the counts."""
        item_ids, error = _bulk_item_ids(request.data)
        if error:
            return error
        custom_list, error = _get_editable_list(request, list_id)
        if error:
            return error
        if custom_list.is_smart:
            return Response(
                {"detail": "Smart lists cannot be edited directly."},
                status=HTTP.FORBIDDEN,
            )
        result = list_actions.add_items_to_list(request.user, custom_list, item_ids)
        return Response(
            {
                "added": result.added,
                "already_present": result.already_present,
                "skipped": result.skipped,
            },
            status=HTTP.OK,
        )


# --- /api/v1/lists/{list_id}/export/ ----------------------------------------


class ListExportCsvView(drf_views.APIView):
    """Download one list as CSV, in the format the list import reads."""

    @extend_schema(
        operation_id="exportListCsv",
        responses={
            (200, "text/csv"): OpenApiTypes.STR,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, list_id):
        """Stream the list's CSV."""
        custom_list = CustomList.objects.filter(id=list_id).first()
        if custom_list is None or not custom_list.user_can_view(request.user):
            return Response({"detail": "List not found."}, status=HTTP.NOT_FOUND)
        filename = slugify(custom_list.name) or "list"
        return StreamingHttpResponse(
            exports.generate_list_csv(custom_list),
            content_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
        )


# --- /api/v1/lists/import/ --------------------------------------------------


class ListImportRequestSerializer(serializers.Serializer):
    """A list CSV, as exported by the list export."""

    file = serializers.FileField()


class ListImportView(drf_views.APIView):
    """Import one list from CSV in the background as a new list."""

    parser_classes = [MultiPartParser]

    @extend_schema(
        operation_id="importListCsv",
        request={"multipart/form-data": ListImportRequestSerializer},
        responses={
            202: TaskQueuedSerializer,
            400: DetailErrorSerializer,
            503: DetailErrorSerializer,
            507: DetailErrorSerializer,
        },
    )
    def post(self, request):
        """Stage the upload and queue the import; poll the returned task."""
        upload = request.FILES.get("file")
        if not upload:
            return Response(
                {"detail": "A CSV upload is required in 'file'."},
                status=HTTP.BAD_REQUEST,
            )
        try:
            staged_file = str(stage_uploaded_file(upload))
        except OSError:
            logger.exception("Could not stage list CSV upload")
            return Response(
                {"detail": "The upload could not be staged."},
                status=HTTP.INSUFFICIENT_STORAGE,
            )
        try:
            task = enqueue_staged_task(
                list_tasks.import_list_csv_task,
                request.user.id,
                staged_file,
                "new",
                staged_paths=(staged_file,),
            )
        except Exception:
            logger.exception("Could not queue list CSV import")
            return Response(
                {"detail": "The import could not be queued."},
                status=HTTP.SERVICE_UNAVAILABLE,
            )
        return Response({"task_id": task.id}, status=HTTP.ACCEPTED)
