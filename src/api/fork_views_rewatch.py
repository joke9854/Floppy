"""Rewatch passes for shows and seasons (P1-D; the web's `media_rewatch`).

A pass makes plays logged at or after its start count as the new watch-through,
while the earlier plays stay as history. Starting and stopping never creates
or deletes plays.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import cache_utils
from app.models import TV, Item, MediaTypes
from app.models.tv import RewatchAlreadyCompleteError
from app.services import metadata_resolution

from .contract_serializers import DetailErrorSerializer
from .helpers import get_tracked_season


class RewatchSeasonSerializer(serializers.Serializer):
    """One season's pass."""

    season_number = serializers.IntegerField()
    started_at = serializers.DateTimeField(allow_null=True)


class RewatchStateSerializer(serializers.Serializer):
    """Whether a pass is open and since when."""

    rewatching = serializers.BooleanField()
    started_at = serializers.DateTimeField(
        allow_null=True,
        help_text="For a show, the earliest open season pass.",
    )
    seasons = RewatchSeasonSerializer(
        many=True,
        help_text="Shows only: every season (specials excluded) and its pass.",
    )


class RewatchStartRequestSerializer(serializers.Serializer):
    """When the pass starts."""

    started_at = serializers.DateTimeField(
        required=False,
        help_text=(
            "ISO 8601 date-time with a UTC offset, not in the future. "
            "Defaults to now."
        ),
    )


class RewatchStartResultSerializer(RewatchStateSerializer):
    """The state after starting, plus the seasons left alone."""

    skipped_seasons = serializers.ListField(
        child=serializers.IntegerField(),
        help_text="Seasons already fully watched from `started_at`, left as they were.",
    )


_RESPONSES_404 = OpenApiResponse(
    DetailErrorSerializer,
    description="The user does not track this show or season.",
)


def _parse_started_at(raw_value):
    """Return (aware datetime, error Response or None)."""
    if raw_value in (None, ""):
        return timezone.now(), None
    parsed = parse_datetime(str(raw_value)) if isinstance(raw_value, str) else None
    if parsed is None or timezone.is_naive(parsed):
        return None, Response(
            {"detail": "started_at must be an ISO 8601 date-time with a UTC offset."},
            status=HTTP.BAD_REQUEST,
        )
    if parsed > timezone.now():
        return None, Response(
            {"detail": "started_at cannot be in the future."},
            status=HTTP.BAD_REQUEST,
        )
    return parsed, None


def _show_state(tv):
    seasons = sorted(
        (
            season
            for season in tv.seasons.select_related("item").all()
            if (season.item.season_number or 0) > 0
        ),
        key=lambda season: season.item.season_number,
    )
    open_starts = [
        season.rewatch_started_at
        for season in seasons
        if season.rewatch_started_at is not None
    ]
    return {
        "rewatching": bool(open_starts),
        "started_at": min(open_starts) if open_starts else None,
        "seasons": [
            {
                "season_number": season.item.season_number,
                "started_at": season.rewatch_started_at,
            }
            for season in seasons
        ],
    }


def _season_state(season):
    return {
        "rewatching": season.rewatch_started_at is not None,
        "started_at": season.rewatch_started_at,
        "seasons": [],
    }


_SCHEMA = {
    "get": extend_schema(responses={200: RewatchStateSerializer, 404: _RESPONSES_404}),
    "post": extend_schema(
        request=RewatchStartRequestSerializer,
        responses={
            200: RewatchStartResultSerializer,
            400: DetailErrorSerializer,
            404: _RESPONSES_404,
            409: OpenApiResponse(
                DetailErrorSerializer,
                description=(
                    "Nothing to rewatch from that date, or every season is "
                    "already being rewatched; code `conflict`."
                ),
            ),
        },
    ),
    "delete": extend_schema(
        responses={200: RewatchStateSerializer, 404: _RESPONSES_404},
    ),
}


class _RewatchView(drf_views.APIView):
    """Shared GET/POST/DELETE; subclasses find the tracked row."""

    def _tracked(self, request, **kwargs):
        raise NotImplementedError

    def _state(self, media):
        raise NotImplementedError

    @_SCHEMA["get"]
    def get(self, request, **kwargs):
        """Return whether a pass is open."""
        media, error = self._tracked(request, **kwargs)
        if error is not None:
            return error
        return Response(self._state(media), status=HTTP.OK)

    @_SCHEMA["post"]
    def post(self, request, **kwargs):
        """Open a pass from `started_at` (default now)."""
        media, error = self._tracked(request, **kwargs)
        if error is not None:
            return error
        data = request.data if isinstance(request.data, dict) else {}
        started_at, error = _parse_started_at(data.get("started_at"))
        if error is not None:
            return error
        try:
            skipped = media.start_rewatch(started_at=started_at) or []
        except RewatchAlreadyCompleteError as error:
            return Response(
                {"detail": str(error), "code": "conflict"},
                status=HTTP.CONFLICT,
            )
        cache_utils.clear_media_list_cache_for_user(request.user.id)
        media.refresh_from_db()
        return Response(
            {
                **self._state(media),
                "skipped_seasons": sorted(
                    season.item.season_number for season in skipped
                ),
            },
            status=HTTP.OK,
        )

    @_SCHEMA["delete"]
    def delete(self, request, **kwargs):
        """Close the open pass(es); plays logged during the pass stay."""
        media, error = self._tracked(request, **kwargs)
        if error is not None:
            return error
        media.stop_rewatch()
        cache_utils.clear_media_list_cache_for_user(request.user.id)
        media.refresh_from_db()
        return Response(self._state(media), status=HTTP.OK)


@extend_schema_view(
    get=extend_schema(operation_id="getShowRewatch"),
    post=extend_schema(operation_id="startShowRewatch"),
    delete=extend_schema(operation_id="stopShowRewatch"),
)
class ShowRewatchView(_RewatchView):
    """Rewatch pass of a whole show: one pass per season (specials excluded).

    Seasons already fully watched from the start date, dropped seasons and
    seasons with an open pass are left as they are.
    """

    def _tracked(self, request, media_type, source, media_id):
        if media_type not in {MediaTypes.TV.value, MediaTypes.ANIME.value}:
            return None, Response(
                {"detail": "Only shows and seasons can be rewatched."},
                status=HTTP.BAD_REQUEST,
            )
        lookup = {
            "media_id": media_id,
            "source": source,
            "media_type": metadata_resolution.get_tracking_media_type(
                media_type, source=source
            ),
        }
        if metadata_resolution.is_grouped_anime_route(media_type, source=source):
            lookup["library_media_type"] = MediaTypes.ANIME.value
        item = Item.objects.filter(**lookup).first()
        if item is None or item.media_type != MediaTypes.TV.value:
            return None, Response(
                {"detail": "Show not tracked."}, status=HTTP.NOT_FOUND
            )
        tv = TV.objects.filter(item=item, user=request.user).order_by("id").first()
        if tv is None:
            return None, Response(
                {"detail": "Show not tracked."}, status=HTTP.NOT_FOUND
            )
        return tv, None

    def _state(self, media):
        return _show_state(media)


@extend_schema_view(
    get=extend_schema(operation_id="getSeasonRewatch"),
    post=extend_schema(operation_id="startSeasonRewatch"),
    delete=extend_schema(operation_id="stopSeasonRewatch"),
)
class SeasonRewatchView(_RewatchView):
    """Rewatch pass of one season."""

    def _tracked(self, request, media_type, source, media_id, season_number):
        if media_type not in {MediaTypes.TV.value, MediaTypes.ANIME.value}:
            return None, Response(
                {"detail": "Only shows and seasons can be rewatched."},
                status=HTTP.BAD_REQUEST,
            )
        season = get_tracked_season(request.user, media_id, source, int(season_number))
        if season is None:
            return None, Response(
                {"detail": "Season not tracked."}, status=HTTP.NOT_FOUND
            )
        return season, None

    def _state(self, media):
        return _season_state(media)
