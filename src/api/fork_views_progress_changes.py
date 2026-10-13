"""Ordered change feed for resume progress.

Mirrors the watched-state feed deliberately: same cursor semantics, same
checkpoint proof, same cursor-expired contract. A client that implements one
implements the other, and the retention machinery is shared rather than forked.
"""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.services.progress_changes import (
    PROGRESS_RESOURCE,
    progress_changes_since,
    retained_progress_range,
)
from integrations.models import SyncBinding
from integrations.state.checkpoints import record_applied_position

from .contract_serializers import DetailErrorSerializer
from .fork_views_watched_state import CursorExpiredSerializer

logger = logging.getLogger(__name__)

MAX_CHANGE_PAGE = 500


class ProgressChangeSerializer(serializers.Serializer):
    """One entry in the resume-progress change feed."""

    sequence = serializers.IntegerField()
    kind = serializers.CharField()
    position_seconds = serializers.FloatField(allow_null=True)
    duration_seconds = serializers.FloatField(allow_null=True)
    completed = serializers.BooleanField(allow_null=True)
    media_id = serializers.CharField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    media_type = serializers.CharField(allow_null=True)
    origin_key = serializers.CharField(allow_blank=True, allow_null=True)
    correlation_id = serializers.CharField()


class ProgressChangeFeedResponseSerializer(serializers.Serializer):
    """A page of the resume-progress change feed."""

    results = ProgressChangeSerializer(many=True)
    next_cursor = serializers.IntegerField(
        help_text="Pass as `cursor` to fetch the next page.",
    )
    has_more = serializers.BooleanField()
    oldest_sequence = serializers.IntegerField(allow_null=True)
    newest_sequence = serializers.IntegerField(allow_null=True)


# /api/v1/sync/progress-changes/
class ProgressChangeFeedView(drf_views.APIView):
    """Serve the ordered resume-progress change feed."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="cursor",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Return changes after this sequence; defaults to 0.",
            ),
            OpenApiParameter(
                name="limit",
                type=int,
                location=OpenApiParameter.QUERY,
                description="Maximum changes per page; defaults to 100, maximum 500.",
            ),
            OpenApiParameter(
                name="connection",
                type=str,
                location=OpenApiParameter.QUERY,
                description=(
                    "`connection` value from `POST /sync/connections/`. Naming "
                    "it records the cursor as this connection's applied position."
                ),
            ),
        ],
        responses={
            200: ProgressChangeFeedResponseSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="`cursor` or `limit` is not an integer.",
            ),
            409: OpenApiResponse(
                CursorExpiredSerializer,
                description="The cursor was compacted away; read a fresh snapshot.",
            ),
        },
    )
    def get(self, request):
        """Return progress changes after a cursor, in server order."""
        raw_cursor = request.query_params.get("cursor", "0")
        try:
            cursor = int(raw_cursor)
        except ValueError:
            return Response(
                {"detail": "cursor must be an integer sequence."},
                status=HTTP.BAD_REQUEST,
            )

        try:
            limit = min(int(request.query_params.get("limit", 100)), MAX_CHANGE_PAGE)
        except ValueError:
            return Response(
                {"detail": "limit must be an integer."},
                status=HTTP.BAD_REQUEST,
            )

        oldest, newest = retained_progress_range(request.user)
        if oldest is not None and 0 < cursor < oldest - 1:
            return Response(
                {
                    "code": "cursor_expired",
                    "detail": (
                        "This cursor is older than the retained change log. "
                        "Read the current progress snapshot and resume from "
                        "its sequence."
                    ),
                    "oldest_sequence": oldest,
                    "newest_sequence": newest,
                },
                status=HTTP.CONFLICT,
            )

        binding = self._acknowledging_binding(request)
        if binding is not None and cursor > 0:
            record_applied_position(binding, cursor, resource=PROGRESS_RESOURCE)

        changes = progress_changes_since(request.user, cursor, limit=limit)
        results = [
            {
                "sequence": change.sequence,
                "kind": change.kind,
                "position_seconds": change.position_seconds,
                "duration_seconds": change.duration_seconds,
                "completed": change.completed,
                "media_id": change.item.media_id if change.item else None,
                "source": change.item.source if change.item else None,
                "media_type": change.item.media_type if change.item else None,
                "origin_key": change.origin_key,
                "correlation_id": str(change.correlation_id),
            }
            for change in changes
        ]

        return Response(
            {
                "results": results,
                "next_cursor": results[-1]["sequence"] if results else cursor,
                "has_more": len(results) == limit,
                "oldest_sequence": oldest,
                "newest_sequence": newest,
            },
            status=HTTP.OK,
        )

    @staticmethod
    def _acknowledging_binding(request):
        """Return the binding this pull speaks for, if it names one."""
        origin_key = request.query_params.get("connection")
        if not origin_key:
            return None
        return SyncBinding.objects.filter(
            user=request.user,
            origin_key=origin_key,
        ).first()
