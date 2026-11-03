"""REST endpoints for personal TV episode ordering."""

from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from app.episode_order_views import available_orders, owned_tv, selected_order
from app.models import EpisodeOrder
from app.services import episode_ordering

from .contract_serializers import DetailErrorSerializer


class EpisodeOrderOptionSerializer(serializers.Serializer):
    """One episode order a provider offers for the series."""

    key = serializers.CharField()
    label = serializers.CharField()
    provider = serializers.ChoiceField(choices=["tmdb", "tvdb"])
    series_id = serializers.CharField()


class EpisodeOrderListSerializer(serializers.Serializer):
    """Available orders and the one currently applied."""

    active = serializers.IntegerField(allow_null=True)
    orders = EpisodeOrderOptionSerializer(many=True)
    errors = serializers.ListField(child=serializers.CharField())


class EpisodeOrderResolutionSerializer(serializers.Serializer):
    """Which provider episodes a group of watches maps to."""

    watch_ids = serializers.ListField(child=serializers.IntegerField())
    episode_ids = serializers.ListField(child=serializers.CharField())
    archive = serializers.BooleanField()


class EpisodeOrderWatchSerializer(serializers.Serializer):
    """One episode watch the change would move."""

    id = serializers.IntegerField()
    item_id = serializers.IntegerField(allow_null=True)
    related_season_id = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    watch_operation_id = serializers.UUIDField(allow_null=True)
    start_date = serializers.DateTimeField(allow_null=True)
    end_date = serializers.DateTimeField(allow_null=True)
    score = serializers.FloatField(allow_null=True)
    notes = serializers.CharField()
    dropped = serializers.BooleanField()
    status = serializers.CharField()


class EpisodeOrderPreviewSerializer(serializers.Serializer):
    """Proposed mapping; send ``token`` and ``resolutions`` back to apply it."""

    order_id = serializers.IntegerField()
    token = serializers.CharField()
    resolutions = EpisodeOrderResolutionSerializer(many=True)
    watches = EpisodeOrderWatchSerializer(many=True)


class EpisodeOrderAppliedSerializer(serializers.Serializer):
    """The applied change."""

    change_id = serializers.IntegerField()
    active_order = serializers.IntegerField()


class EpisodeOrderChangeRequestSerializer(serializers.Serializer):
    """Preview (``provider`` + ``key``) or apply (``order_id`` + ``token``)."""

    action = serializers.CharField(
        required=False,
        help_text="`preview` (default); any other value applies the change.",
    )
    provider = serializers.ChoiceField(choices=["tmdb", "tvdb"], required=False)
    key = serializers.CharField(required=False)
    order_id = serializers.IntegerField(required=False)
    token = serializers.CharField(required=False)
    resolutions = EpisodeOrderResolutionSerializer(many=True, required=False)


class EpisodeOrderView(APIView):
    """List provider orders and apply an explicit history reconciliation."""

    @extend_schema(
        responses={200: EpisodeOrderListSerializer, 404: DetailErrorSerializer},
    )
    def get(self, request, tv_id):
        """Return currently available provider orders for one tracked show."""
        tv = owned_tv(request.user, tv_id)
        orders, errors = available_orders(tv, request.user)
        return Response({"active": tv.active_episode_order_id, "orders": orders, "errors": errors})

    @extend_schema(
        request=EpisodeOrderChangeRequestSerializer,
        responses={
            200: PolymorphicProxySerializer(
                component_name="EpisodeOrderChangeResponse",
                serializers=[
                    EpisodeOrderPreviewSerializer,
                    EpisodeOrderAppliedSerializer,
                ],
                resource_type_field_name=None,
            ),
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def post(self, request, tv_id):
        """Preview or apply an order change using stable provider identities."""
        tv = owned_tv(request.user, tv_id)
        action = request.data.get("action", "preview")
        try:
            if action == "preview":
                order = selected_order(
                    tv, request.user, request.data.get("provider"), request.data.get("key"),
                )
                preview = episode_ordering.preview_change(tv, order)
                return Response({"order_id": order.pk, **preview})
            order = EpisodeOrder.objects.get(pk=request.data.get("order_id"), show=tv.item)
            journal = episode_ordering.apply_change(
                tv,
                order,
                token=request.data.get("token", ""),
                resolutions=request.data.get("resolutions") or [],
            )
            return Response({"change_id": journal.pk, "active_order": order.pk})
        except EpisodeOrder.DoesNotExist:
            return Response({"detail": "Episode order not found."}, status=status.HTTP_404_NOT_FOUND)
        except (ValueError, TypeError, KeyError) as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
