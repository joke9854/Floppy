# FORK: metadata-management and score endpoints mirroring web-only actions
# (metadata_sync_views, score_views). URL wiring lives in fork_urls.py.
import logging
from http import HTTPStatus as HTTP  # noqa: N814

from django.apps import apps
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import custom_metadata
from app import metadata_sync_views as web_metadata_views
from app.models import (
    Item,
    MediaTypes,
    MetadataProviderPreference,
    Sources,
)
from app.services import metadata_resolution
from app.services.metadata_projection import project_item_metadata

from .contract_serializers import DetailErrorSerializer
from .helpers import (
    apply_episode_score,
    check_valid_type,
    get_tracked_season,
    resolve_episode_coordinate_for_request,
    validate_episode_score,
)
from .schema import MEDIA_TYPE_PARAM, MEDIA_TYPE_TV_ONLY_PARAM

logger = logging.getLogger(__name__)


def _owned_media_queryset(user, item):
    """Return the user's tracked-media rows for an item.

    Episode rows have no `user` column -- ownership is inherited from the
    related season -- so filtering them by `user=` raises FieldError and turns
    every episode metadata override into a 500.
    """
    media_model = apps.get_model("app", item.media_type)
    if item.media_type == MediaTypes.EPISODE.value:
        return media_model.objects.filter(related_season__user=user, item=item)
    return media_model.objects.filter(user=user, item=item)


def _get_owned_tracked_item(user, item_id):
    """Return the Item if the user tracks it, else None."""
    item = Item.objects.filter(id=item_id).first()
    if item is None:
        return None
    if not _owned_media_queryset(user, item).exists():
        return None
    return item


class ItemImageRequestSerializer(serializers.Serializer):
    """New artwork URL for the item."""

    image_url = serializers.CharField()


class ItemImageSerializer(serializers.Serializer):
    """The item's artwork after the change."""

    id = serializers.IntegerField()
    image = serializers.CharField()


class ItemMetadataIdentitySerializer(serializers.Serializer):
    """Which item the projection describes."""

    media_id = serializers.CharField()
    source = serializers.CharField()
    media_type = serializers.CharField()
    season_number = serializers.IntegerField(allow_null=True)
    episode_number = serializers.IntegerField(allow_null=True)
    external_ids = serializers.DictField(
        help_text="Resolved ids keyed by external provider.",
    )


class ItemMetadataAttributionSerializer(serializers.Serializer):
    """The provider the stored metadata came from."""

    source = serializers.CharField()
    source_url = serializers.CharField(allow_null=True)


class ItemMetadataFreshnessSerializer(serializers.Serializer):
    """When the stored metadata was last refreshed."""

    refreshed_at = serializers.DateTimeField(allow_null=True)
    age_days = serializers.IntegerField(allow_null=True)
    state = serializers.ChoiceField(choices=["fresh", "stale", "unknown"])


class ItemMetadataFieldsSerializer(serializers.Serializer):
    """Stored provider fields; empty values are omitted."""

    title = serializers.CharField(required=False)
    original_title = serializers.CharField(required=False)
    synopsis = serializers.CharField(required=False)
    image = serializers.CharField(required=False)
    release_datetime = serializers.DateTimeField(required=False)
    runtime_minutes = serializers.IntegerField(required=False)
    genres = serializers.ListField(child=serializers.CharField(), required=False)
    country = serializers.CharField(required=False)
    languages = serializers.ListField(child=serializers.CharField(), required=False)
    studios = serializers.ListField(child=serializers.CharField(), required=False)
    format = serializers.CharField(required=False)
    status = serializers.CharField(required=False)


class ItemMetadataSerializer(serializers.Serializer):
    """Normalized metadata projection for an item."""

    identity = ItemMetadataIdentitySerializer()
    attribution = ItemMetadataAttributionSerializer()
    freshness = ItemMetadataFreshnessSerializer()
    fields = ItemMetadataFieldsSerializer()
    authorship = serializers.CharField()


# Accepted keys are app.custom_metadata field specs, which vary by media type.
_METADATA_OVERRIDE_REQUEST = {
    "application/json": {
        "type": "object",
        "additionalProperties": True,
        "description": "Manual metadata fields such as title, synopsis or genres.",
    },
}


class ItemMetadataUpdateSerializer(serializers.Serializer):
    """Fields changed by a metadata override."""

    id = serializers.IntegerField()
    updated_fields = serializers.ListField(child=serializers.CharField())


class ProviderPreferenceSerializer(serializers.Serializer):
    """Preferred metadata provider and the available choices."""

    provider = serializers.CharField(allow_null=True)
    available_providers = serializers.ListField(child=serializers.CharField())


class ProviderPreferenceRequestSerializer(serializers.Serializer):
    """Metadata provider to prefer."""

    provider = serializers.CharField()


class ProviderPreferenceUpdateSerializer(serializers.Serializer):
    """Preferred provider after the change."""

    provider = serializers.CharField()


class ProviderPreferenceErrorSerializer(DetailErrorSerializer):
    """Unavailable provider, with the allowed choices."""

    available_providers = serializers.ListField(
        child=serializers.CharField(), required=False
    )


class EpisodeScoreRequestSerializer(serializers.Serializer):
    """New episode score on the raw 0-10 scale, or null to clear it."""

    score = serializers.DecimalField(max_digits=3, decimal_places=1, allow_null=True)


class EpisodeScoreSerializer(serializers.Serializer):
    """The episode's score after the change."""

    score = serializers.CharField(allow_null=True)


# /api/v1/metadata/items/[item_id]/image/
class ItemImageView(drf_views.APIView):
    """Override the stored image URL for a tracked item."""

    @extend_schema(
        request=ItemImageRequestSerializer,
        responses={
            200: ItemImageSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def patch(self, request, item_id):
        """Set the item's image URL (mirrors web update_item_image)."""
        item = _get_owned_tracked_item(request.user, item_id)
        if item is None:
            return Response(
                {"detail": "Item not found in your library."},
                status=HTTP.NOT_FOUND,
            )

        image_url = (request.data.get("image_url") or "").strip()
        if not image_url:
            return Response(
                {"detail": "'image_url' is required."},
                status=HTTP.BAD_REQUEST,
            )

        if item.image != image_url:
            item.image = image_url
            item.save(update_fields=["image"])
        return Response(
            {"id": item.id, "image": item.image},
            status=HTTP.OK,
        )


# /api/v1/metadata/items/[item_id]/
class ItemMetadataView(drf_views.APIView):
    """Read a normalized projection, or override custom metadata."""

    @extend_schema(
        responses={
            200: ItemMetadataSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, item_id):
        """Return the normalized projection with attribution and freshness."""
        item = _get_owned_tracked_item(request.user, item_id)
        if item is None:
            return Response(
                {"detail": "Item not found in your library."},
                status=HTTP.NOT_FOUND,
            )

        return Response(project_item_metadata(item), status=HTTP.OK)

    @extend_schema(
        request=_METADATA_OVERRIDE_REQUEST,
        responses={
            200: ItemMetadataUpdateSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def patch(self, request, item_id):
        """Apply custom-metadata overrides (mirrors update_manual_item_metadata)."""
        item = _get_owned_tracked_item(request.user, item_id)
        if item is None:
            return Response(
                {"detail": "Item not found in your library."},
                status=HTTP.NOT_FOUND,
            )

        if not custom_metadata.supports_custom_metadata(item):
            return Response(
                {"detail": "Metadata overrides are not available for this item."},
                status=HTTP.BAD_REQUEST,
            )

        form = custom_metadata.ManualMetadataForm(request.data, item=item)
        if not form.is_valid():
            return Response(
                {"detail": "Invalid metadata.", "errors": form.errors},
                status=HTTP.BAD_REQUEST,
            )
        update_fields = form.save()
        return Response(
            {"id": item.id, "updated_fields": sorted(update_fields or [])},
            status=HTTP.OK,
        )


# /api/v1/media/[media_type]/[source]/[media_id]/provider-preference/
class MediaProviderPreferenceView(drf_views.APIView):
    """Read or set the metadata display-provider override for an item."""

    def _get_item(self, media_type, source, media_id):
        tracking_media_type = metadata_resolution.get_tracking_media_type(
            media_type,
            source=source,
        )
        lookup = {
            "media_id": media_id,
            "source": source,
            "media_type": tracking_media_type,
        }
        if metadata_resolution.is_grouped_anime_route(media_type, source=source):
            lookup["library_media_type"] = MediaTypes.ANIME.value
        return Item.objects.filter(**lookup).first()

    @extend_schema(
        parameters=[MEDIA_TYPE_PARAM],
        responses={
            200: ProviderPreferenceSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, media_type, source, media_id):
        """Return the current provider preference and available options."""
        if not check_valid_type(media_type):
            return Response(
                {"detail": "Unsupported media type."},
                status=HTTP.BAD_REQUEST,
            )
        item = self._get_item(media_type, source, media_id)
        if item is None:
            return Response({"detail": "Item not found."}, status=HTTP.NOT_FOUND)
        preference = MetadataProviderPreference.objects.filter(
            user=request.user,
            item=item,
        ).first()
        options = [
            choice.value
            for choice in metadata_resolution.available_metadata_provider_options(
                media_type,
                identity_provider=item.source,
            )
        ]
        return Response(
            {
                "provider": preference.provider if preference else None,
                "available_providers": options,
            },
            status=HTTP.OK,
        )

    @extend_schema(
        parameters=[MEDIA_TYPE_PARAM],
        request=ProviderPreferenceRequestSerializer,
        responses={
            200: ProviderPreferenceUpdateSerializer,
            400: ProviderPreferenceErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, media_type, source, media_id):
        """Set the provider override (mirrors update_metadata_provider_preference)."""
        if not check_valid_type(media_type):
            return Response(
                {"detail": "Unsupported media type."},
                status=HTTP.BAD_REQUEST,
            )
        item = self._get_item(media_type, source, media_id)
        if item is None:
            return Response({"detail": "Item not found."}, status=HTTP.NOT_FOUND)

        provider = (request.data.get("provider") or "").strip()
        allowed_providers = {
            choice.value
            for choice in metadata_resolution.available_metadata_provider_options(
                media_type,
                identity_provider=item.source,
            )
        }
        if provider not in allowed_providers:
            return Response(
                {
                    "detail": "That metadata provider is not available for this title.",
                    "available_providers": sorted(allowed_providers),
                },
                status=HTTP.BAD_REQUEST,
            )

        supports_custom = custom_metadata.supports_custom_provider(media_type)
        if provider == Sources.MANUAL.value and supports_custom:
            current_display_metadata = (
                web_metadata_views._resolve_current_display_metadata_payload(
                    user=request.user,
                    item=item,
                    media_type=media_type,
                    media_id=media_id,
                    source=source,
                )
            )
            custom_metadata.snapshot_custom_metadata(item, current_display_metadata)

        MetadataProviderPreference.objects.update_or_create(
            user=request.user,
            item=item,
            defaults={"provider": provider},
        )
        return Response({"provider": provider}, status=HTTP.OK)


# /api/v1/media/[...]/[season_number]/episodes/[episode_number]/score/
class MediaEpisodeScoreView(drf_views.APIView):
    """Set or clear the score on all plays of an episode."""

    @extend_schema(
        parameters=[MEDIA_TYPE_TV_ONLY_PARAM],
        request=EpisodeScoreRequestSerializer,
        responses={
            200: EpisodeScoreSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def patch(
        self,
        request,
        media_type,
        source,
        media_id,
        season_number,
        episode_number,
    ):
        """Update the episode score (mirrors web update_episode_score).

        Body: {"score": 8.5} or {"score": null} to clear. Scores use the raw
        0-10 storage scale like the other media score fields in this API.
        """
        if media_type != MediaTypes.TV.value:
            return Response(
                {"detail": "Episodes are supported only for 'tv' media type."},
                status=HTTP.BAD_REQUEST,
            )

        try:
            _, coordinate_error = resolve_episode_coordinate_for_request(
                request.user,
                media_id,
                source,
                season_number,
                episode_number,
                language=metadata_resolution.metadata_language_default(request.user),
            )
        except Exception as error:
            return Response(
                {"detail": "Could not resolve episode.", "errors": str(error)},
                status=HTTP.NOT_FOUND,
            )
        if coordinate_error:
            return coordinate_error

        season = get_tracked_season(request.user, media_id, source, season_number)
        if season is None:
            return Response(
                {"detail": "Season not found or not tracked."},
                status=HTTP.NOT_FOUND,
            )

        if "score" not in request.data:
            return Response(
                {"detail": "'score' is required (number or null)."},
                status=HTTP.BAD_REQUEST,
            )
        score, error = validate_episode_score(request.data.get("score"))
        if error:
            return error

        if not apply_episode_score(season, episode_number, score):
            return Response(
                {"detail": "Episode not tracked."},
                status=HTTP.NOT_FOUND,
            )

        return Response(
            {"score": str(score) if score is not None else None},
            status=HTTP.OK,
        )
