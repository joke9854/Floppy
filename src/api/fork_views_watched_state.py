# FORK: canonical watched-state endpoints for external synchronizing clients.
# Deliberately separate from the playback and history endpoints: setting
# unwatched is not deleting history, and the two must not share a route.
import datetime
import logging
from http import HTTPStatus as HTTP  # noqa: N814

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import WatchStateOrigin, WatchStateSequence
from app.services.progress_changes import (
    PROGRESS_RESOURCE,
    retained_progress_range,
)
from app.services.sync_activity import activity_snapshot
from app.services.watch_state import (
    RevisionConflictError,
    changes_since,
    effective_state,
    record_state_change,
    retained_change_range,
)
from integrations.models import (
    OutboundDeliveryStatus,
    StateConflict,
    StateConflictStatus,
    SyncBinding,
    SyncCheckpoint,
    SyncClientKind,
    SyncDirection,
)
from integrations.state.checkpoints import (
    WATCHED_STATE_RESOURCE,
    record_applied_position,
)
from integrations.state.identity import (
    activate_binding,
    deactivate_binding,
    get_or_create_binding,
)

from .contract_serializers import DetailErrorSerializer
from .helpers import (
    check_source_type,
    check_valid_type,
    resolve_item_queryset,
    try_parse_datetime_input,
)

logger = logging.getLogger(__name__)

MAX_CHANGE_PAGE = 200
WATCHED_AT_FUTURE_TOLERANCE = datetime.timedelta(minutes=5)


def _serialize_state(state, item):
    """Return the public shape of one canonical state."""
    if state is None:
        return {
            "media_id": item.media_id,
            "source": item.source,
            "media_type": item.media_type,
            "watched": False,
            "play_count": 0,
            "first_watched_at": None,
            "last_watched_at": None,
            "revision": 0,
            "conflicted": False,
            "provenance": None,
        }

    return {
        "media_id": item.media_id,
        "source": item.source,
        "media_type": item.media_type,
        "watched": state.watched,
        "play_count": state.play_count,
        "first_watched_at": state.first_watched_at,
        "last_watched_at": state.last_watched_at,
        "revision": state.revision,
        "conflicted": state.conflicted,
        "provenance": {
            # Explicit and inferred manual changes stay distinguishable: a
            # client showing "you marked this watched" must not say so about a
            # state Floppy inferred from a reconciliation pass.
            "origin_kind": state.origin_kind,
            "origin_key": state.origin_key,
            "updated_at": state.updated_at,
        },
    }


def _resolve_item(request, media_type, source, media_id):
    """Return the addressed item, or an error response."""
    if not check_valid_type(media_type):
        return None, Response(
            {"detail": f"Invalid media type: {media_type}"},
            status=HTTP.BAD_REQUEST,
        )
    if not check_source_type(media_type, source):
        return None, Response(
            {"detail": f"Cannot query `{source}` for `{media_type}` media type"},
            status=HTTP.BAD_REQUEST,
        )

    season_number = request.query_params.get("season_number")
    episode_number = request.query_params.get("episode_number")
    try:
        season_number = int(season_number) if season_number is not None else None
        episode_number = int(episode_number) if episode_number is not None else None
    except (TypeError, ValueError):
        return None, Response(
            {"detail": "season_number and episode_number must be integers."},
            status=HTTP.BAD_REQUEST,
        )

    queryset = resolve_item_queryset(
        media_id,
        source,
        media_type,
        season_number=season_number,
        episode_number=episode_number,
        library_media_type=request.query_params.get("library_media_type"),
    )

    # More than one candidate means the address was ambiguous. Picking one
    # would eventually write to the wrong library bucket.
    matches = list(queryset[:2])
    if not matches:
        return None, Response(
            {"detail": "No matching item."},
            status=HTTP.NOT_FOUND,
        )
    if len(matches) > 1:
        return None, Response(
            {"detail": "Ambiguous item; pass library_media_type."},
            status=HTTP.CONFLICT,
        )
    return matches[0], None


class WatchedStateProvenanceSerializer(serializers.Serializer):
    """Who last changed a watched state, and when."""

    origin_kind = serializers.CharField(
        help_text="Explicit and inferred changes stay distinguishable.",
    )
    origin_key = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()


class WatchedStateResponseSerializer(serializers.Serializer):
    """Canonical watched state of one item."""

    media_id = serializers.CharField()
    source = serializers.CharField()
    media_type = serializers.CharField()
    watched = serializers.BooleanField()
    play_count = serializers.IntegerField()
    first_watched_at = serializers.DateTimeField(allow_null=True)
    last_watched_at = serializers.DateTimeField(allow_null=True)
    revision = serializers.IntegerField(
        help_text="Monotonic per-item revision; usable as `If-Match` on PUT.",
    )
    conflicted = serializers.BooleanField()
    provenance = WatchedStateProvenanceSerializer(
        allow_null=True,
        help_text="Null when the item has never had a recorded state.",
    )


class WatchedStateWriteResponseSerializer(WatchedStateResponseSerializer):
    """Watched state after an explicit assertion."""

    replayed = serializers.BooleanField(
        help_text="True when the idempotency key matched an earlier change.",
    )
    unchanged = serializers.BooleanField(
        help_text="True when the assertion matched the existing state.",
    )


class WatchedStateRequestSerializer(serializers.Serializer):
    """Body for asserting a watched state."""

    watched = serializers.BooleanField(help_text="Must be a JSON boolean.")
    watched_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text=(
            "Exact ISO-8601 instant of the watch; only read when `watched` is "
            "true. Defaults to the server's current time and may not be in the "
            "future."
        ),
    )
    play_count = serializers.IntegerField(required=False, allow_null=True)
    client_event_id = serializers.CharField(
        required=False,
        help_text="Idempotency key; the `Idempotency-Key` header takes precedence.",
    )


class WatchedStateRevisionConflictSerializer(serializers.Serializer):
    """Body of a 409 when `If-Match` does not match the current revision."""

    detail = serializers.CharField()
    revision = serializers.IntegerField(help_text="The current revision.")


class WatchedStateChangeSerializer(serializers.Serializer):
    """One entry in the watched-state change feed."""

    sequence = serializers.IntegerField()
    revision = serializers.IntegerField()
    previous_revision = serializers.IntegerField(allow_null=True)
    kind = serializers.CharField()
    watched = serializers.BooleanField(allow_null=True)
    play_count = serializers.IntegerField(allow_null=True)
    watched_at = serializers.DateTimeField(allow_null=True)
    media_id = serializers.CharField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    media_type = serializers.CharField(allow_null=True)
    season_number = serializers.IntegerField(
        allow_null=True,
        help_text="Null for anything that is not an episode.",
    )
    episode_number = serializers.IntegerField(allow_null=True)
    origin_kind = serializers.CharField()
    correlation_id = serializers.CharField()


class ChangeFeedResponseSerializer(serializers.Serializer):
    """A page of an ordered change feed."""

    results = WatchedStateChangeSerializer(many=True)
    next_cursor = serializers.IntegerField(
        help_text="Pass as `cursor` to fetch the next page.",
    )
    has_more = serializers.BooleanField()
    oldest_sequence = serializers.IntegerField(allow_null=True)
    newest_sequence = serializers.IntegerField(allow_null=True)


class CursorExpiredSerializer(serializers.Serializer):
    """Body of a 409 when the client's cursor was compacted away."""

    code = serializers.CharField(help_text="Always `cursor_expired`.")
    detail = serializers.CharField()
    oldest_sequence = serializers.IntegerField()
    newest_sequence = serializers.IntegerField(allow_null=True)


class SyncCheckpointSerializer(serializers.Serializer):
    """Where one connection has got to for one resource and direction."""

    resource = serializers.CharField()
    direction = serializers.CharField()
    last_sequence = serializers.IntegerField()
    behind_by = serializers.IntegerField(allow_null=True)
    updated_at = serializers.DateTimeField()


class SyncConnectionStatusSerializer(serializers.Serializer):
    """Health and capabilities of one connection."""

    id = serializers.IntegerField()
    client_kind = serializers.CharField()
    label = serializers.CharField()
    status = serializers.CharField()
    directions = serializers.ListField(child=serializers.CharField())
    capabilities = serializers.ListField(child=serializers.CharField())
    unavailable_capabilities = serializers.ListField(
        child=serializers.CharField(),
        help_text="Approved capabilities the adapter cannot provide.",
    )
    origin_key = serializers.CharField(
        help_text="Pass as `connection` when pulling a change feed.",
    )
    last_reconciled_at = serializers.DateTimeField(allow_null=True)
    last_error_message = serializers.CharField(allow_blank=True, allow_null=True)
    pending_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    open_conflicts = serializers.IntegerField()
    unresolved_references = serializers.IntegerField()
    checkpoints = SyncCheckpointSerializer(many=True)


class SyncConnectionListResponseSerializer(serializers.Serializer):
    """All connections of the caller."""

    results = SyncConnectionStatusSerializer(many=True)


class SyncConflictSerializer(serializers.Serializer):
    """One open disagreement waiting for a person."""

    id = serializers.IntegerField()
    reason = serializers.CharField()
    media_id = serializers.CharField()
    source = serializers.CharField()
    media_type = serializers.CharField()
    client_kind = serializers.CharField()
    local = serializers.JSONField(help_text="Snapshot of Floppy's state.")
    remote = serializers.JSONField(help_text="Snapshot of the connection's state.")
    base = serializers.JSONField(help_text="Snapshot both sides last agreed on.")
    occurrence_count = serializers.IntegerField()
    updated_at = serializers.DateTimeField()


class SyncConflictListResponseSerializer(serializers.Serializer):
    """Open conflicts."""

    results = SyncConflictSerializer(many=True)


class SyncConflictResolveRequestSerializer(serializers.Serializer):
    """Body for resolving a conflict."""

    watched = serializers.BooleanField(help_text="Must be a JSON boolean.")
    play_count = serializers.IntegerField(required=False, allow_null=True)


_WATCHED_STATE_ITEM_PARAMS = [
    OpenApiParameter(
        name="season_number",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Season of the addressed episode.",
    ),
    OpenApiParameter(
        name="episode_number",
        type=int,
        location=OpenApiParameter.QUERY,
        description="Episode number of the addressed episode.",
    ),
    OpenApiParameter(
        name="library_media_type",
        type=str,
        location=OpenApiParameter.QUERY,
        description="Disambiguates an item that exists in several library buckets.",
    ),
]

_CHANGE_FEED_PARAMS = [
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
            "`connection` value from `POST /sync/connections/`. Naming it "
            "records the cursor as this connection's applied position."
        ),
    ),
]


# /api/v1/media/[media_type]/[source]/[media_id]/watched-state/
class WatchedStateView(drf_views.APIView):
    """Read or set the canonical watched state for one item."""

    @extend_schema(
        parameters=_WATCHED_STATE_ITEM_PARAMS,
        responses={
            200: WatchedStateResponseSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Invalid address."),
            404: OpenApiResponse(DetailErrorSerializer, description="No matching item."),
            409: OpenApiResponse(
                DetailErrorSerializer,
                description="Ambiguous item; pass `library_media_type`.",
            ),
        },
    )
    def get(self, request, media_type, source, media_id):
        """Return effective state and its provenance."""
        item, error = _resolve_item(request, media_type, source, media_id)
        if error is not None:
            return error

        state = effective_state(request.user, item)
        return Response(_serialize_state(state, item), status=HTTP.OK)

    @extend_schema(
        parameters=[
            *_WATCHED_STATE_ITEM_PARAMS,
            OpenApiParameter(
                name="If-Match",
                type=int,
                location=OpenApiParameter.HEADER,
                description="Expected current revision; a mismatch answers 409.",
            ),
            OpenApiParameter(
                name="Idempotency-Key",
                type=str,
                location=OpenApiParameter.HEADER,
                description="Replays with the same key return the first result.",
            ),
        ],
        request=WatchedStateRequestSerializer,
        responses={
            200: WatchedStateWriteResponseSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="Invalid address or body.",
            ),
            404: OpenApiResponse(DetailErrorSerializer, description="No matching item."),
            409: OpenApiResponse(
                WatchedStateRevisionConflictSerializer,
                description=(
                    "Revision conflict (body has `revision`), or an ambiguous "
                    "item (body has only `detail`)."
                ),
            ),
        },
    )
    def put(self, request, media_type, source, media_id):
        """Set watched state explicitly.

        This is a state assertion, not a play. It records no playback session
        and removes no history, which is what keeps "mark unwatched" distinct
        from "delete history".
        """
        item, error = _resolve_item(request, media_type, source, media_id)
        if error is not None:
            return error

        watched = request.data.get("watched")
        if not isinstance(watched, bool):
            return Response(
                {"detail": "`watched` must be a boolean."},
                status=HTTP.BAD_REQUEST,
            )

        watched_at = timezone.now()
        raw_watched_at = request.data.get("watched_at")
        if watched and raw_watched_at is not None:
            # Exact instant of the watch; the default stays "now".
            invalid = Response(
                {"detail": "`watched_at` must be an ISO-8601 datetime."},
                status=HTTP.BAD_REQUEST,
            )
            if not isinstance(raw_watched_at, str):
                return invalid
            try:
                watched_at = try_parse_datetime_input(raw_watched_at)
            except (TypeError, ValueError):
                return invalid
            if watched_at > timezone.now() + WATCHED_AT_FUTURE_TOLERANCE:
                return Response(
                    {"detail": "`watched_at` cannot be in the future."},
                    status=HTTP.BAD_REQUEST,
                )

        expected_revision = request.headers.get("If-Match")
        if expected_revision is not None:
            try:
                expected_revision = int(expected_revision)
            except ValueError:
                return Response(
                    {"detail": "If-Match must be an integer revision."},
                    status=HTTP.BAD_REQUEST,
                )

        idempotency_key = request.headers.get("Idempotency-Key") or request.data.get(
            "client_event_id",
        )

        # Re-asserting "watched" keeps the time it was first marked, so a
        # repeated request is recognised as unchanged instead of recording a
        # new change whenever the clock has ticked into another second.
        current = effective_state(request.user, item)
        play_count = request.data.get("play_count")
        already_watched = bool(
            current
            and current.watched
            and (play_count is None or play_count == current.play_count),
        )
        try:
            result = record_state_change(
                request.user,
                item,
                watched=watched,
                play_count=play_count,
                # An explicit watched_at is the exact instant and is always kept;
                # without one, re-asserting an already-watched state keeps the
                # stored time so a retry is reported as unchanged.
                watched_at=(
                    watched_at
                    if watched and (raw_watched_at is not None or not already_watched)
                    else None
                ),
                origin_kind=WatchStateOrigin.LOCAL_API.value,
                origin_key="api",
                origin_event_id=idempotency_key,
                expected_revision=expected_revision,
            )
        except RevisionConflictError as error:
            return Response(
                {
                    "detail": str(error),
                    "revision": effective_state(request.user, item).revision,
                },
                status=HTTP.CONFLICT,
            )

        payload = _serialize_state(
            result.state or effective_state(request.user, item),
            item,
        )
        payload["replayed"] = result.replayed
        payload["unchanged"] = result.unchanged
        return Response(payload, status=HTTP.OK)


# /api/v1/sync/changes/
class WatchedStateChangeFeedView(drf_views.APIView):
    """Serve the ordered change feed for a synchronizing client."""

    @extend_schema(
        parameters=_CHANGE_FEED_PARAMS,
        responses={
            200: ChangeFeedResponseSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="`cursor` or `limit` is not an integer.",
            ),
            409: OpenApiResponse(
                CursorExpiredSerializer,
                description="The cursor was compacted away; take a fresh snapshot.",
            ),
        },
    )
    def get(self, request):
        """Return changes after a cursor, in server order.

        The cursor is a server sequence, which is allocated at commit time, so
        paginating by it cannot skip a change that committed late.
        """
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

        oldest, newest = retained_change_range(request.user)
        if oldest is not None and 0 < cursor < oldest - 1:
            # The client's position was compacted away. Serving the remaining
            # tail would look like a successful catch-up while silently
            # dropping everything between its cursor and what is left.
            return Response(
                {
                    "code": "cursor_expired",
                    "detail": (
                        "This cursor is older than the retained change log. "
                        "Take a fresh snapshot and resume from its sequence."
                    ),
                    "oldest_sequence": oldest,
                    "newest_sequence": newest,
                },
                status=HTTP.CONFLICT,
            )

        # Asking for changes after N is the client's proof it applied through N.
        # The server cannot know that any earlier, and advancing on delivery
        # would skip whatever a client fetched but died before applying.
        binding = self._acknowledging_binding(request)
        if binding is not None and cursor > 0:
            record_applied_position(binding, cursor)

        changes = changes_since(request.user, cursor, limit=limit)
        results = [
            {
                "sequence": change.sequence,
                "revision": change.revision,
                "previous_revision": change.previous_revision,
                "kind": change.kind,
                "watched": change.watched,
                "play_count": change.play_count,
                "watched_at": change.watched_at,
                "media_id": change.item.media_id if change.item else None,
                "source": change.item.source if change.item else None,
                "media_type": change.item.media_type if change.item else None,
                # Episode coordinates, so a client can place an episode change
                # without a second lookup. Null for anything that is not one.
                "season_number": change.item.season_number if change.item else None,
                "episode_number": (change.item.episode_number if change.item else None),
                "origin_kind": change.origin_kind,
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
        """Return the binding this pull speaks for, if it names one.

        Identified by origin key so a client can hold several connections
        without them sharing a checkpoint. Unnamed pulls still work; they just
        record no position, and so never let the log compact past them.
        """
        origin_key = request.query_params.get("connection")
        if not origin_key:
            return None
        return SyncBinding.objects.filter(
            user=request.user,
            origin_key=origin_key,
        ).first()


class AppConnectionRequestSerializer(serializers.Serializer):
    """Body for registering an app as a pull client."""

    client = serializers.RegexField(
        r"^[a-z0-9_-]{1,32}$",
        help_text="Short client slug, for example `cinetrack`.",
    )
    instance_key = serializers.CharField(
        min_length=1,
        max_length=128,
        help_text="Stable per-install identifier, chosen by the client.",
    )
    label = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=255,
        help_text="Display name; defaults to the client slug.",
    )


class AppConnectionSerializer(serializers.Serializer):
    """A registered app connection and where its cursor should start."""

    connection = serializers.CharField(
        help_text="Pass as `connection` when pulling the change feeds.",
    )
    client = serializers.CharField()
    instance_key = serializers.CharField()
    oldest_sequence = serializers.IntegerField(allow_null=True)
    newest_sequence = serializers.IntegerField(
        help_text="Start the cursor here after taking a full snapshot.",
    )


def _app_instance_key(client, instance_key):
    """Return the stored instance key for an app connection.

    The slug is folded in so the same install id under two client slugs stays
    two connections.
    """
    return f"{client}:{instance_key}"


# /api/v1/sync/connections/
class SyncConnectionsView(drf_views.APIView):
    """Report what each connection is actually allowed and able to do."""

    @extend_schema(
        request=AppConnectionRequestSerializer,
        responses={
            200: AppConnectionSerializer,
            201: AppConnectionSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Invalid body."),
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="Connection stopped by an administrator.",
            ),
        },
    )
    def post(self, request):
        """Register this app as a pull client of the change feeds.

        Turns the user's change log on, because changes are only recorded while
        a connection is operational. The binding is pull-only: it is approved
        for the Floppy-to-client direction and for no capability, so the
        outbound delivery engine has nothing to write to it.
        """
        body = AppConnectionRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        client = body.validated_data["client"]
        instance_key = body.validated_data["instance_key"]
        requested_label = body.validated_data.get("label")

        binding, _created = get_or_create_binding(
            request.user,
            SyncClientKind.APP.value,
            instance_key=_app_instance_key(client, instance_key),
            label=requested_label or client,
        )
        if binding.kill_switch:
            return Response(
                {"detail": "This connection was stopped by an administrator."},
                status=HTTP.FORBIDDEN,
            )

        already_active = binding.is_operational()
        if not already_active:
            activate_binding(
                binding,
                capabilities=[],
                directions=[SyncDirection.OUTBOUND.value],
            )
        if requested_label and binding.label != requested_label:
            binding.label = requested_label
            binding.save(update_fields=["label", "updated_at"])

        oldest, newest = retained_change_range(request.user)
        if newest is None:
            # Nothing retained is not "nothing ever happened": a compacted log
            # still has an allocator position the cursor must not fall behind.
            sequence = WatchStateSequence.objects.filter(user=request.user).first()
            newest = sequence.last_sequence if sequence else 0

        return Response(
            {
                "connection": binding.origin_key,
                "client": client,
                "instance_key": instance_key,
                "oldest_sequence": oldest,
                "newest_sequence": newest,
            },
            status=HTTP.OK if already_active else HTTP.CREATED,
        )

    @extend_schema(responses={200: SyncConnectionListResponseSerializer})
    def get(self, request):
        """Return connections, their directions, and unavailable capabilities."""
        from integrations.state.outbound import get_adapter

        _, newest_watched = retained_change_range(request.user)
        _, newest_progress = retained_progress_range(request.user)
        newest_by_resource = {
            WATCHED_STATE_RESOURCE: newest_watched,
            PROGRESS_RESOURCE: newest_progress,
        }

        results = []
        for binding in SyncBinding.objects.filter(user=request.user):
            adapter = get_adapter(binding)
            supported = set(adapter.CAPABILITIES) if adapter is not None else set()
            approved = set(binding.approved_capabilities or [])

            results.append(
                {
                    "id": binding.pk,
                    "client_kind": binding.client_kind,
                    "label": binding.label,
                    "status": binding.status,
                    "directions": binding.approved_directions or [],
                    "capabilities": sorted(approved & supported),
                    # Named explicitly rather than omitted: a direction the
                    # user asked for and cannot have is a capability
                    # limitation, and saying nothing reads as success.
                    "unavailable_capabilities": sorted(approved - supported),
                    # A client needs this to name itself when pulling a change
                    # feed; without it no checkpoint can ever be recorded, and
                    # the change log can never compact.
                    "origin_key": binding.origin_key,
                    "last_reconciled_at": binding.last_reconciled_at,
                    "last_error_message": binding.last_error_message,
                    "pending_deliveries": binding.deliveries.filter(
                        status=OutboundDeliveryStatus.PENDING.value,
                    ).count(),
                    # Counted separately and never folded into "pending": a
                    # failed write that reads as still-in-progress is the
                    # silent failure this whole surface exists to prevent.
                    "failed_deliveries": binding.deliveries.filter(
                        status=OutboundDeliveryStatus.FAILED.value,
                    ).count(),
                    "open_conflicts": binding.conflicts.filter(
                        status=StateConflictStatus.OPEN.value,
                    ).count(),
                    "unresolved_references": binding.unresolved_references.filter(
                        dismissed_at__isnull=True,
                    ).count(),
                    "checkpoints": self._checkpoints(binding, newest_by_resource),
                },
            )

        return Response({"results": results}, status=HTTP.OK)

    @staticmethod
    def _checkpoints(binding, newest_by_resource):
        """Report where this connection has got to, and how far behind it is.

        "Behind" is the number the user actually acts on: a connection that
        looks healthy but sits ten thousand changes back is not working, and
        neither a status field nor a last-seen timestamp shows that.
        """
        rows = []
        for checkpoint in SyncCheckpoint.objects.filter(binding=binding):
            newest = newest_by_resource.get(checkpoint.resource)
            rows.append(
                {
                    "resource": checkpoint.resource,
                    "direction": checkpoint.direction,
                    "last_sequence": checkpoint.last_sequence,
                    "behind_by": (
                        max(newest - checkpoint.last_sequence, 0)
                        if newest is not None
                        else None
                    ),
                    "updated_at": checkpoint.updated_at,
                },
            )
        return rows


# /api/v1/sync/connections/[connection]/
class SyncConnectionDetailView(drf_views.APIView):
    """Remove one app connection."""

    @extend_schema(
        responses={
            204: OpenApiResponse(description="Connection removed."),
            404: OpenApiResponse(
                DetailErrorSerializer,
                description="No such app connection for this account.",
            ),
        },
    )
    def delete(self, request, connection):
        """Stop recording changes for an app connection.

        Only the caller's own app connections are addressable; provider
        bindings are managed in the web UI and answer 404 here, as does
        another user's connection.
        """
        binding = SyncBinding.objects.filter(
            user=request.user,
            origin_key=connection,
            client_kind=SyncClientKind.APP.value,
        ).first()
        if binding is None:
            return Response(
                {"detail": "No such connection."},
                status=HTTP.NOT_FOUND,
            )

        deactivate_binding(binding)
        return Response(status=HTTP.NO_CONTENT)


class SyncActivitiesSerializer(serializers.Serializer):
    """When each area of the account last changed."""

    all = serializers.DateTimeField(allow_null=True)
    watched = serializers.DateTimeField(allow_null=True)
    playback = serializers.DateTimeField(allow_null=True)
    library = serializers.DateTimeField(allow_null=True)
    lists = serializers.DateTimeField(allow_null=True)
    collection = serializers.DateTimeField(allow_null=True)
    removed = serializers.DateTimeField(allow_null=True)


# /api/v1/sync/activities/
class SyncActivitiesView(drf_views.APIView):
    """Tell a pull client which areas changed since it last looked."""

    @extend_schema(responses={200: SyncActivitiesSerializer})
    def get(self, request):
        """Return the last-changed time per area, ISO-8601 UTC, or null."""
        snapshot = activity_snapshot(request.user)
        return Response(
            {
                key: (
                    value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
                    if value is not None
                    else None
                )
                for key, value in snapshot.items()
            },
            status=HTTP.OK,
        )


# /api/v1/sync/conflicts/
class SyncConflictsView(drf_views.APIView):
    """List disagreements waiting for a person."""

    @extend_schema(responses={200: SyncConflictListResponseSerializer})
    def get(self, request):
        """Return open conflicts."""
        conflicts = StateConflict.objects.filter(
            user=request.user,
            status=StateConflictStatus.OPEN.value,
        ).select_related("item", "binding")

        return Response(
            {
                "results": [
                    {
                        "id": conflict.pk,
                        "reason": conflict.reason,
                        "media_id": conflict.item.media_id,
                        "source": conflict.item.source,
                        "media_type": conflict.item.media_type,
                        "client_kind": conflict.binding.client_kind,
                        "local": conflict.local_snapshot,
                        "remote": conflict.remote_snapshot,
                        "base": conflict.base_snapshot,
                        "occurrence_count": conflict.occurrence_count,
                        "updated_at": conflict.updated_at,
                    }
                    for conflict in conflicts
                ],
            },
            status=HTTP.OK,
        )


# /api/v1/sync/conflicts/[conflict_id]/resolve/
class SyncConflictResolveView(drf_views.APIView):
    """Settle one disagreement with the state a person chose."""

    @extend_schema(
        request=SyncConflictResolveRequestSerializer,
        responses={
            200: WatchedStateResponseSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Invalid body."),
            404: OpenApiResponse(
                DetailErrorSerializer,
                description="No open conflict with that id.",
            ),
        },
    )
    def post(self, request, conflict_id):
        """Resolve a conflict, creating a new revision."""
        from integrations.state.apply import resolve_conflict

        conflict = StateConflict.objects.filter(
            pk=conflict_id,
            user=request.user,
            status=StateConflictStatus.OPEN.value,
        ).first()
        if conflict is None:
            return Response(
                {"detail": "No open conflict with that id."},
                status=HTTP.NOT_FOUND,
            )

        watched = request.data.get("watched")
        if not isinstance(watched, bool):
            return Response(
                {"detail": "`watched` must be a boolean."},
                status=HTTP.BAD_REQUEST,
            )

        result = resolve_conflict(
            conflict,
            watched=watched,
            play_count=request.data.get("play_count"),
        )

        return Response(
            _serialize_state(result.state, conflict.item),
            status=HTTP.OK,
        )
