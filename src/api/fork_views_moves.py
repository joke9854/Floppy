"""Move tracked shows between provider ids and libraries (P1-D).

The web's `move_library_item` and `migrate_grouped_anime`. Both move one
user's tracking (plays, statuses, ratings) to another item in one
transaction; nothing changes when they fail.
"""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from django.db import OperationalError
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import cache_utils
from app.db_retry import is_retryable_error, run_retryable_db_operation
from app.models import Item, MediaTypes, Sources
from app.providers import credentials
from app.services import anime_migration, library_migration, metadata_resolution

from .contract_serializers import DetailErrorSerializer
from .provider_errors import (
    PROVIDER_UNAVAILABLE_DETAIL,
    is_provider_failure,
    is_provider_not_found,
    provider_unavailable_response,
)

logger = logging.getLogger(__name__)

DATABASE_BUSY_RETRY_SECONDS = 5


class MoveRequestSerializer(serializers.Serializer):
    """Where to move the show."""

    target_media_type = serializers.ChoiceField(choices=["tv", "anime"])
    target_source = serializers.CharField()
    target_media_id = serializers.CharField()


class AnimeMigrationRequestSerializer(serializers.Serializer):
    """Which provider's grouped series to migrate into."""

    provider = serializers.ChoiceField(choices=["tmdb", "tvdb"])


class MovedTitleSerializer(serializers.Serializer):
    """The title now holding the user's tracking."""

    media_type = serializers.CharField(help_text="Library: `tv` or `anime`.")
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField()


_RESPONSES = {
    200: MovedTitleSerializer,
    400: OpenApiResponse(
        DetailErrorSerializer,
        description="The move is not possible; `detail` says why. Nothing changed.",
    ),
    404: DetailErrorSerializer,
    503: OpenApiResponse(
        DetailErrorSerializer,
        description=(
            f"{PROVIDER_UNAVAILABLE_DETAIL} (code `provider_unavailable`), or the "
            "database is busy (code `database_busy`). Both carry `Retry-After`; "
            "nothing changed."
        ),
    ),
}


def _moved(user, item):
    return {
        "media_type": library_migration.library_bucket(item),
        "source": item.source,
        "media_id": str(item.media_id),
        "title": item.get_display_title(user) or item.title or "",
    }


def _database_busy_response():
    response = Response(
        {
            "detail": "The database is busy with another operation. Nothing was changed.",
            "code": "database_busy",
        },
        status=HTTP.SERVICE_UNAVAILABLE,
    )
    response["Retry-After"] = str(DATABASE_BUSY_RETRY_SECONDS)
    return response


def _failure_response(error):
    """400 with the service's own message, or 503 when a provider caused it."""
    cause = error.__cause__ or error.__context__
    if (
        cause is not None
        and is_provider_failure(cause)
        and not is_provider_not_found(cause)
    ):
        return provider_unavailable_response()
    return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)


class MediaMoveView(drf_views.APIView):
    """Move the user's tracking of a show to another provider id or library.

    Moves between TV Shows and Anime and between TMDB, TVDB and MAL ids;
    flat MAL anime can move only to grouped TV metadata.
    """

    @extend_schema(
        operation_id="moveTrackedShow",
        request=MoveRequestSerializer,
        responses=_RESPONSES,
    )
    def post(self, request, media_type, source, media_id):
        """Move the tracking and return where it now lives."""
        if media_type not in {MediaTypes.TV.value, MediaTypes.ANIME.value}:
            return Response(
                {"detail": "Only TV Shows and Anime entries can be moved."},
                status=HTTP.BAD_REQUEST,
            )
        data = request.data if isinstance(request.data, dict) else {}
        target_media_type = str(data.get("target_media_type") or "").strip()
        target_source = str(data.get("target_source") or "").strip()
        target_media_id = str(data.get("target_media_id") or "").strip()
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
        if item is None:
            return Response({"detail": "Show not tracked."}, status=HTTP.NOT_FOUND)

        with credentials.current_user_scope(request.user):
            try:
                target_item = run_retryable_db_operation(
                    lambda: library_migration.migrate_library_item(
                        request.user,
                        item,
                        target_media_type,
                        target_source,
                        target_media_id,
                    ),
                    operation_name="TV/Anime library migration",
                ).value
            except OperationalError as error:
                if not is_retryable_error(error):
                    raise
                return _database_busy_response()
            except library_migration.LibraryMigrationError as error:
                return _failure_response(error)
        cache_utils.clear_media_list_cache_for_user(request.user.id)
        return Response(_moved(request.user, target_item), status=HTTP.OK)


class AnimeGroupedMigrationView(drf_views.APIView):
    """Convert a flat MAL anime into grouped TV-style tracking.

    Finds every flat MAL entry of the same series through the chosen
    provider's mapping and moves them into one grouped show with seasons.
    """

    @extend_schema(
        operation_id="migrateAnimeToGrouped",
        request=AnimeMigrationRequestSerializer,
        responses=_RESPONSES,
    )
    def post(self, request, media_id):
        """Migrate and return the grouped show."""
        data = request.data if isinstance(request.data, dict) else {}
        provider = str(data.get("provider") or "").strip()
        if provider not in {Sources.TMDB.value, Sources.TVDB.value}:
            return Response(
                {"detail": "provider must be 'tmdb' or 'tvdb'."},
                status=HTTP.BAD_REQUEST,
            )
        item = Item.objects.filter(
            media_id=media_id,
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
        ).first()
        if item is None:
            return Response({"detail": "Anime not found."}, status=HTTP.NOT_FOUND)
        with credentials.current_user_scope(request.user):
            try:
                result = anime_migration.migrate_flat_anime_to_grouped(
                    request.user,
                    item,
                    provider,
                )
            except anime_migration.AnimeMigrationError as error:
                return _failure_response(error)
        cache_utils.clear_media_list_cache_for_user(request.user.id)
        return Response(_moved(request.user, result.grouped_tv.item), status=HTTP.OK)
