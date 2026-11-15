"""Watched-state sync settings per connection (P1-H).

The web Integrations page's direction choice and pause switch for each
provider connection (Jellyfin, Plex, ...). Changing them approves or
withdraws a provider's access to the user's watched state, so no token may:
the writes are scoped `NEVER`, like credential management.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from integrations.models import SyncBinding
from integrations.state import settings_view

from .contract_serializers import DetailErrorSerializer


class SyncCapabilitySerializer(serializers.Serializer):
    """One thing a connection may do."""

    code = serializers.CharField()
    label = serializers.CharField()
    approved = serializers.BooleanField()
    supported = serializers.BooleanField()
    unavailable = serializers.BooleanField(
        help_text="Approved, but the provider's adapter cannot do it yet.",
    )


class SyncSettingSerializer(serializers.Serializer):
    """One connection's sync settings and health."""

    id = serializers.IntegerField()
    client_kind = serializers.CharField()
    label = serializers.CharField()
    status = serializers.CharField()
    is_operational = serializers.BooleanField()
    kill_switch = serializers.BooleanField(help_text="Paused by the user.")
    direction = serializers.ChoiceField(choices=list(settings_view.DIRECTION_LABELS))
    capabilities = SyncCapabilitySerializer(many=True)
    has_adapter = serializers.BooleanField()
    can_write = serializers.BooleanField()
    last_reconciled_at = serializers.DateTimeField(allow_null=True)
    last_error_message = serializers.CharField(allow_blank=True, allow_null=True)
    pending_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    open_conflicts = serializers.IntegerField()


class SyncSettingListSerializer(serializers.Serializer):
    """Every connection's sync settings."""

    results = SyncSettingSerializer(many=True)


class SyncSettingUpdateSerializer(serializers.Serializer):
    """Fields to change."""

    direction = serializers.ChoiceField(
        choices=list(settings_view.DIRECTION_LABELS), required=False
    )
    kill_switch = serializers.BooleanField(required=False)


class SyncSettingUpdatedSerializer(SyncSettingSerializer):
    """The connection after the change."""

    partially_granted = serializers.BooleanField(
        help_text=(
            "The adapter supports only part of the chosen direction; the rest "
            "is listed as unavailable."
        ),
    )


_ROW_FIELDS = (
    "id",
    "client_kind",
    "label",
    "status",
    "is_operational",
    "kill_switch",
    "direction",
    "has_adapter",
    "can_write",
    "last_reconciled_at",
    "last_error_message",
    "pending_deliveries",
    "failed_deliveries",
    "open_conflicts",
)


def _row_payload(row):
    return {
        **{field: row[field] for field in _ROW_FIELDS},
        "capabilities": row["capability_rows"],
    }


def _rows(user):
    return {row["id"]: _row_payload(row) for row in settings_view.binding_rows(user)}


class SyncSettingsView(drf_views.APIView):
    """Every connection's direction, pause switch and health."""

    @extend_schema(
        operation_id="listSyncSettings",
        responses={200: SyncSettingListSerializer},
    )
    def get(self, request):
        """Return the connections."""
        return Response({"results": list(_rows(request.user).values())}, status=HTTP.OK)


class SyncSettingDetailView(drf_views.APIView):
    """Change one connection's direction or pause it."""

    @extend_schema(
        operation_id="updateSyncSetting",
        request=SyncSettingUpdateSerializer,
        responses={
            200: SyncSettingUpdatedSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
            409: OpenApiResponse(
                DetailErrorSerializer,
                description="The connection can do nothing in that direction.",
            ),
        },
    )
    def patch(self, request, binding_id):
        """Apply the direction and pause switch sent."""
        binding = SyncBinding.objects.filter(pk=binding_id, user=request.user).first()
        if binding is None:
            return Response(
                {"detail": "That connection no longer exists."},
                status=HTTP.NOT_FOUND,
            )
        data = request.data if isinstance(request.data, dict) else {}
        kill_switch = data.get("kill_switch")
        if "kill_switch" in data and not isinstance(kill_switch, bool):
            return Response(
                {"detail": "kill_switch must be a boolean."},
                status=HTTP.BAD_REQUEST,
            )
        partially_granted = False
        if "direction" in data:
            try:
                partially_granted = settings_view.set_binding_direction(
                    binding, data["direction"]
                )
            except settings_view.DirectionNotSupportedError:
                return Response(
                    {
                        "detail": (
                            f"{binding.get_client_kind_display()} cannot do that "
                            "yet. Its adapter reports no matching capability."
                        ),
                        "code": "conflict",
                    },
                    status=HTTP.CONFLICT,
                )
            except ValueError:
                return Response(
                    {"detail": "Unknown synchronization direction."},
                    status=HTTP.BAD_REQUEST,
                )
        if "kill_switch" in data:
            binding.kill_switch = kill_switch
            binding.save(update_fields=["kill_switch", "updated_at"])
        row = _rows(request.user)[binding.pk]
        return Response(
            {**row, "partially_granted": partially_granted},
            status=HTTP.OK,
        )
