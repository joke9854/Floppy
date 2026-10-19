"""Character pictures for CineTrack's cast row, read through Floppy's TVDB key."""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import MediaTypes, Sources
from app.providers import credentials, services, tmdb, tvdb

from .contract_serializers import DetailErrorSerializer

logger = logging.getLogger(__name__)

class CineTrackCharacterSerializer(serializers.Serializer):
    """One on-screen character with its TVDB pictures."""

    name = serializers.CharField()
    person_name = serializers.CharField()
    person_id = serializers.CharField()
    character_image = serializers.CharField(allow_null=True)
    person_image = serializers.CharField(allow_null=True)
    sort = serializers.IntegerField(allow_null=True)


class CineTrackCharactersResponseSerializer(serializers.Serializer):
    """Characters of one title; ``reason`` explains an empty list."""

    tvdb_id = serializers.CharField(allow_null=True)
    reason = serializers.CharField(required=False)
    characters = CineTrackCharacterSerializer(many=True)


def _tvdb_id(media_type, source, media_id):
    """Return the TVDB id of a TMDB or TVDB title, or None when TVDB has no match."""
    if source == Sources.TVDB.value:
        return str(media_id)
    # Only TMDB's small external_ids record: the full title took 5-60 s for
    # titles Floppy had never fetched, and CineTrack gave up waiting.
    external_ids = tmdb.external_ids(media_type, media_id)
    if media_type == MediaTypes.TV.value:
        tvdb_id = str(external_ids.get("tvdb_id") or "").strip()
        # Rare: TMDB lists no TVDB id, so fall back to the slower title match.
        return tvdb_id or tmdb.resolve_tvdb_id_for_tmdb_show(media_id, tv_data=tmdb.tv(media_id))
    imdb_id = str(external_ids.get("imdb_id") or "").strip()
    return tvdb.movie_id_for_imdb(imdb_id) if imdb_id else None


class MediaCharactersView(drf_views.APIView):
    """On-screen characters with character and actor pictures from TVDB.

    Read-only. An empty list with a ``reason`` means there is nothing to show
    (TVDB not configured, or no TVDB match); provider failures return 503.
    """

    @extend_schema(
        responses={
            200: CineTrackCharactersResponseSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Unsupported media type or source."),
            503: OpenApiResponse(DetailErrorSerializer, description="TMDB or TVDB could not be reached."),
        },
    )
    def get(self, request, media_type, source, media_id):
        """Return the title's characters, or an empty list with a reason."""
        if media_type not in {MediaTypes.TV.value, MediaTypes.MOVIE.value}:
            return Response({"detail": "Characters are supported only for 'tv' and 'movie'."}, status=HTTP.BAD_REQUEST)
        if source not in {Sources.TMDB.value, Sources.TVDB.value}:
            return Response({"detail": "source must be 'tmdb' or 'tvdb'."}, status=HTTP.BAD_REQUEST)
        with credentials.current_user_scope(request.user):
            if not tvdb.enabled(request.user):
                return Response({"tvdb_id": None, "reason": "tvdb_not_configured", "characters": []}, status=HTTP.OK)
            try:
                tvdb_id = _tvdb_id(media_type, source, media_id)
                if not tvdb_id:
                    return Response({"tvdb_id": None, "reason": "no_tvdb_match", "characters": []}, status=HTTP.OK)
                characters = tvdb.character_images(media_type, tvdb_id)
            except services.ProviderAPIError as error:
                logger.warning("CineTrack characters unavailable for %s %s %s: %s", media_type, source, media_id, error.provider)
                return Response({"detail": "Metadata provider unavailable."}, status=HTTP.SERVICE_UNAVAILABLE)
        return Response({"tvdb_id": str(tvdb_id), "characters": characters}, status=HTTP.OK)
