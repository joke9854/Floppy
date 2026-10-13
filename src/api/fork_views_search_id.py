# FORK: look up movies, shows and episodes by external id (IMDb, TMDB, TVDB),
# the way Trakt's and Simkl's id search lets apps map their ids to Floppy's.
import logging
from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

import app.providers.tmdb
from app.models import Item, MediaTypes, Sources
from app.providers.services import ProviderAPIError

from .contract_serializers import DetailErrorSerializer

logger = logging.getLogger(__name__)

_ID_KEYS = ("imdb", "tmdb", "tvdb")
_TYPES = ("movie", "show", "episode")
_ITEM_TYPES = {"movie": MediaTypes.MOVIE.value, "show": MediaTypes.TV.value}
_PROVIDER_KEYS = {"imdb": "imdb_id", "tvdb": "tvdb_id"}


class SearchIdResultSerializer(serializers.Serializer):
    """One item an external id names."""

    type = serializers.ChoiceField(choices=_TYPES)
    source = serializers.CharField()
    media_id = serializers.CharField(help_text="For an episode, its show's id.")
    title = serializers.CharField(allow_null=True)
    year = serializers.IntegerField(allow_null=True)
    season_number = serializers.IntegerField(required=False)
    episode_number = serializers.IntegerField(required=False)


class SearchIdResponseSerializer(serializers.Serializer):
    """Every item the id names; empty when it names nothing."""

    results = SearchIdResultSerializer(many=True)


def _year(value):
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _known_items(key, value, wanted):
    """Return results for items Floppy already stores, without a network call."""
    if key == "tmdb":
        query = {"media_id": value}
    else:
        query = {f"provider_external_ids__{_PROVIDER_KEYS[key]}": value}
    types = [_ITEM_TYPES[t] for t in _ITEM_TYPES if wanted in (None, t)]
    items = (
        Item.objects.filter(source=Sources.TMDB.value, media_type__in=types, **query)
        .order_by("id")
        .values("media_type", "media_id", "title")
    )
    results = []
    seen = set()
    for item in items:
        kind = "movie" if item["media_type"] == MediaTypes.MOVIE.value else "show"
        if (kind, item["media_id"]) in seen:
            continue
        seen.add((kind, item["media_id"]))
        results.append(
            {
                "type": kind,
                "source": Sources.TMDB.value,
                "media_id": item["media_id"],
                "title": item["title"] or None,
                "year": None,
            }
        )
    return results


def _found_items(key, value, wanted):
    """Return results from TMDB's find for an IMDb or TVDB id."""
    found = app.providers.tmdb.find(value, _PROVIDER_KEYS[key]) or {}
    results = []
    if wanted in (None, "movie"):
        results += [
            {
                "type": "movie",
                "source": Sources.TMDB.value,
                "media_id": str(movie["id"]),
                "title": movie.get("title"),
                "year": _year(movie.get("release_date")),
            }
            for movie in found.get("movie_results") or []
        ]
    if wanted in (None, "show"):
        results += [
            {
                "type": "show",
                "source": Sources.TMDB.value,
                "media_id": str(show["id"]),
                "title": show.get("name"),
                "year": _year(show.get("first_air_date")),
            }
            for show in found.get("tv_results") or []
        ]
    if wanted in (None, "episode"):
        results += [
            {
                "type": "episode",
                "source": Sources.TMDB.value,
                "media_id": str(episode["show_id"]),
                "title": episode.get("name"),
                "year": _year(episode.get("air_date")),
                "season_number": episode.get("season_number"),
                "episode_number": episode.get("episode_number"),
            }
            for episode in found.get("tv_episode_results") or []
            if episode.get("show_id") is not None
        ]
    return results


def _tmdb_item(media_id, wanted):
    """Return the TMDB movie or show with this id, or [] when TMDB has none."""
    fetch = app.providers.tmdb.movie if wanted == "movie" else app.providers.tmdb.tv
    try:
        metadata = fetch(media_id)
    except ProviderAPIError as error:
        if error.status_code == HTTP.NOT_FOUND:
            return []
        raise
    return [
        {
            "type": wanted,
            "source": Sources.TMDB.value,
            "media_id": str(media_id),
            "title": metadata.get("title"),
            "year": _year((metadata.get("details") or {}).get("release_date"))
            or _year((metadata.get("details") or {}).get("first_air_date")),
        }
    ]


# /api/v1/search/id/
class SearchIdView(drf_views.APIView):
    """Find the movies, shows and episodes an external id names."""

    @extend_schema(
        description=(
            "Look up an item by exactly one external id. IMDb and TVDB ids "
            "are matched against items Floppy already stores, then against "
            "TMDB; a TMDB id needs 'type' (movie or show), since TMDB reuses "
            "numbers across them. An IMDb or TVDB episode id returns the "
            "episode with its show's id and coordinates."
        ),
        parameters=[
            OpenApiParameter("imdb", str, description="An IMDb id (tt...)."),
            OpenApiParameter("tmdb", str, description="A TMDB id; needs type."),
            OpenApiParameter("tvdb", str, description="A TVDB id."),
            OpenApiParameter(
                "type",
                str,
                enum=list(_TYPES),
                description="Only return this kind of item.",
            ),
        ],
        responses={
            200: SearchIdResponseSerializer,
            400: DetailErrorSerializer,
            502: DetailErrorSerializer,
        },
    )
    def get(self, request):
        """Return the items the id names."""
        given = {
            key: request.query_params.get(key, "").strip()
            for key in _ID_KEYS
            if request.query_params.get(key, "").strip()
        }
        if len(given) != 1:
            return Response(
                {"detail": "Give exactly one of imdb, tmdb, or tvdb."},
                status=HTTP.BAD_REQUEST,
            )
        wanted = request.query_params.get("type") or None
        if wanted is not None and wanted not in _TYPES:
            return Response(
                {"detail": f"'type' must be one of {', '.join(_TYPES)}."},
                status=HTTP.BAD_REQUEST,
            )
        ((key, value),) = given.items()

        if key == "tmdb":
            if wanted not in _ITEM_TYPES:
                return Response(
                    {"detail": "A tmdb id needs type=movie or type=show."},
                    status=HTTP.BAD_REQUEST,
                )
            results = _known_items(key, value, wanted)
            if not results:
                try:
                    results = _tmdb_item(value, wanted)
                except Exception:
                    logger.warning("Search by tmdb id failed", exc_info=True)
                    return Response(
                        {"detail": "The metadata provider could not be reached."},
                        status=HTTP.BAD_GATEWAY,
                    )
            return Response({"results": results}, status=HTTP.OK)

        results = [] if wanted == "episode" else _known_items(key, value, wanted)
        if not results:
            try:
                results = _found_items(key, value, wanted)
            except Exception:
                logger.warning("Search by %s id failed", key, exc_info=True)
                return Response(
                    {"detail": "The metadata provider could not be reached."},
                    status=HTTP.BAD_GATEWAY,
                )
        return Response({"results": results}, status=HTTP.OK)
