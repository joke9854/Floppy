"""Data for the title pages: people, studios, history genres, ratings graphs.

P1-C of docs/plans/floppy-v2.md. Each view returns the data its web page
shows, without presentation (no colors, sort menus or filter state): the
client filters and sorts the full lists itself.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.core.cache import cache
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import people_data
from app.detail_builders import _rating_fields
from app.history_views import collect_history_genres
from app.models import Item, MediaTypes
from app.providers import credentials

from .contract_serializers import DetailErrorSerializer
from .provider_errors import PROVIDER_UNAVAILABLE_DETAIL

_PROVIDER_503 = OpenApiResponse(
    DetailErrorSerializer,
    description=(
        f"{PROVIDER_UNAVAILABLE_DETAIL} Code `provider_unavailable`, with "
        "`Retry-After`."
    ),
)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# --- /api/v1/history/genres/ -------------------------------------------------


class HistoryGenresResponseSerializer(serializers.Serializer):
    """Genre values the history `genre` and `implied_genre` filters accept."""

    genres = serializers.ListField(child=serializers.CharField())
    implied_genres = serializers.ListField(child=serializers.CharField())


class HistoryGenresView(drf_views.APIView):
    """Genres of the user's tracked items, for the history genre filter."""

    @extend_schema(
        operation_id="listHistoryGenres",
        responses={200: HistoryGenresResponseSerializer},
    )
    def get(self, request):
        """Return the user's genres and implied genres, sorted by name."""
        return Response(collect_history_genres(request.user), status=HTTP.OK)


# --- /api/v1/media/{type}/{source}/{id}/ratings-graph/ ----------------------

RATING_SOURCES = {
    "provider": {},
    "trakt": {"use_trakt": True},
    "imdb": {"use_imdb": True},
}
# A poll of a still-pending Trakt graph queues the season fetch at most once
# per this many seconds.
TRAKT_RATINGS_QUEUE_SECONDS = 600


class RatingsGraphEpisodeSerializer(serializers.Serializer):
    """One episode's rating."""

    episode_number = serializers.IntegerField()
    score = serializers.FloatField(allow_null=True)
    votes = serializers.IntegerField()


class RatingsGraphSeasonSerializer(serializers.Serializer):
    """One season with its rated episodes."""

    season_number = serializers.IntegerField()
    score = serializers.FloatField(
        allow_null=True,
        help_text="Stored season rating, when the rating source has one.",
    )
    votes = serializers.IntegerField()
    episodes = RatingsGraphEpisodeSerializer(many=True)


class RatingsGraphResponseSerializer(serializers.Serializer):
    """Ratings of a show by season and episode."""

    rating_source = serializers.ChoiceField(choices=sorted(RATING_SOURCES))
    pending = serializers.BooleanField(
        help_text=(
            "True while Trakt ratings of aired episodes are still being "
            "fetched; poll again later. Always false for other sources."
        ),
    )
    seasons = RatingsGraphSeasonSerializer(many=True)


def _queue_trakt_ratings(source, media_id, season_numbers):
    from app.tasks_trakt import populate_trakt_episode_ratings_for_season

    for season_number in season_numbers:
        key = f"api:trakt-ratings-queued:{source}:{media_id}:{season_number}"
        if cache.add(key, 1, TRAKT_RATINGS_QUEUE_SECONDS):
            populate_trakt_episode_ratings_for_season.delay(
                str(media_id), source, season_number
            )


class MediaRatingsGraphView(drf_views.APIView):
    """Per-episode ratings of a show, as stored by Floppy (no provider call).

    Covers the provider, Trakt and IMDb rating graphs of the detail pages.
    Specials (season 0) are left out unless asked for with `season=0`.
    """

    @extend_schema(
        operation_id="getMediaRatingsGraph",
        parameters=[
            OpenApiParameter(
                name="rating_source",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                enum=sorted(RATING_SOURCES),
                description="Whose ratings to return; defaults to `provider`.",
            ),
            OpenApiParameter(
                name="season",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Only this season.",
            ),
        ],
        responses={
            200: RatingsGraphResponseSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="Not a show, or an invalid parameter.",
            ),
        },
    )
    def get(self, request, media_type, source, media_id):
        """Return each season's episodes with score and vote count."""
        if media_type not in {MediaTypes.TV.value, MediaTypes.ANIME.value}:
            return Response(
                {"detail": "Ratings graphs exist only for 'tv' and 'anime'."},
                status=HTTP.BAD_REQUEST,
            )
        rating_source = request.GET.get("rating_source") or "provider"
        if rating_source not in RATING_SOURCES:
            return Response(
                {"detail": "rating_source must be 'provider', 'trakt' or 'imdb'."},
                status=HTTP.BAD_REQUEST,
            )
        season_number = None
        raw_season = request.GET.get("season")
        if raw_season not in (None, ""):
            season_number = _int_or_none(raw_season)
            if season_number is None or season_number < 0:
                return Response(
                    {"detail": "season must be a non-negative integer."},
                    status=HTTP.BAD_REQUEST,
                )

        rating_field, count_field = _rating_fields(**RATING_SOURCES[rating_source])
        base = Item.objects.filter(media_id=str(media_id), source=source)
        if season_number is None:
            base = base.filter(season_number__gt=0)
        else:
            base = base.filter(season_number=season_number)

        seasons = {}
        for row in base.filter(media_type=MediaTypes.SEASON.value).values(
            "season_number", rating_field, count_field
        ):
            seasons[row["season_number"]] = {
                "season_number": row["season_number"],
                "score": _float_or_none(row[rating_field]),
                "votes": row[count_field] or 0,
                "episodes": [],
            }
        for row in (
            base.filter(media_type=MediaTypes.EPISODE.value)
            .exclude(episode_number__isnull=True)
            .order_by("season_number", "episode_number")
            .values("season_number", "episode_number", rating_field, count_field)
        ):
            season = seasons.setdefault(
                row["season_number"],
                {
                    "season_number": row["season_number"],
                    "score": None,
                    "votes": 0,
                    "episodes": [],
                },
            )
            season["episodes"].append(
                {
                    "episode_number": row["episode_number"],
                    "score": _float_or_none(row[rating_field]),
                    "votes": row[count_field] or 0,
                }
            )

        pending = False
        if rating_source == "trakt":
            from app.providers import trakt

            if trakt.is_configured():
                pending_seasons = sorted(
                    set(
                        base.filter(
                            media_type=MediaTypes.EPISODE.value,
                            trakt_rating__isnull=True,
                            release_datetime__isnull=False,
                            release_datetime__lte=timezone.now(),
                        ).values_list("season_number", flat=True)
                    )
                )
                if pending_seasons:
                    pending = True
                    _queue_trakt_ratings(source, media_id, pending_seasons)

        return Response(
            {
                "rating_source": rating_source,
                "pending": pending,
                "seasons": [seasons[number] for number in sorted(seasons)],
            },
            status=HTTP.OK,
        )


# --- /api/v1/people/{source}/{person_id}/ ------------------------------------


class PersonCreditSerializer(serializers.Serializer):
    """One title in a person's credits."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField()
    image = serializers.CharField()
    year = serializers.IntegerField(allow_null=True)
    role = serializers.CharField(allow_blank=True)
    departments = serializers.ListField(child=serializers.CharField())
    credit_type = serializers.CharField(allow_blank=True)
    vote_average = serializers.FloatField(allow_null=True)
    vote_count = serializers.IntegerField(allow_null=True)
    popularity = serializers.FloatField(allow_null=True)
    item_id = serializers.IntegerField(
        allow_null=True,
        help_text=(
            "Floppy's item id when the title is known to this server (by any "
            "user); null otherwise. Not a sign that this user tracks it."
        ),
    )
    genres = serializers.ListField(
        child=serializers.CharField(),
        help_text="Genres of the Floppy item; empty without `item_id`.",
    )
    implied_genres = serializers.ListField(child=serializers.CharField())
    watched = serializers.BooleanField(help_text="This user watched or read it.")
    watched_minutes = serializers.IntegerField(
        allow_null=True,
        help_text="Minutes this user spent on the person's part of it.",
    )


class PersonProfileSerializer(serializers.Serializer):
    """Who the person is."""

    source = serializers.CharField()
    person_id = serializers.CharField()
    name = serializers.CharField()
    image = serializers.CharField()
    biography = serializers.CharField(allow_blank=True)
    known_for_department = serializers.CharField(allow_blank=True)
    birth_date = serializers.CharField(allow_null=True)
    death_date = serializers.CharField(allow_null=True)
    place_of_birth = serializers.CharField(allow_blank=True)
    is_author = serializers.BooleanField()
    source_url = serializers.CharField()


class PersonWatchedSerializer(serializers.Serializer):
    """What this user watched or read of the person's work."""

    movies = serializers.IntegerField()
    shows = serializers.IntegerField()
    books = serializers.IntegerField(help_text="Books, comics and manga.")
    plays = serializers.IntegerField(allow_null=True)
    minutes = serializers.IntegerField(
        allow_null=True,
        help_text="Null for authors: reading time is not counted per author.",
    )


class PersonDetailResponseSerializer(serializers.Serializer):
    """A person page."""

    person = PersonProfileSerializer()
    credits = PersonCreditSerializer(
        many=True,
        help_text="Every credit, one per title, in the provider's order.",
    )
    watched_credits = PersonCreditSerializer(
        many=True,
        help_text=(
            "Titles this user watched or read; for authors this can include "
            "tracked books the provider did not list."
        ),
    )
    known_for = PersonCreditSerializer(
        many=True,
        help_text="Most-voted on-screen credits, at most ten.",
    )
    watched = PersonWatchedSerializer()


def _credit_payload(entry):
    item = entry.get("tracked_item")
    departments = entry.get("all_departments")
    if departments is None:
        departments = [entry["department"]] if entry.get("department") else []
    return {
        "media_type": entry.get("media_type") or "",
        "source": entry.get("source") or "",
        "media_id": str(entry.get("media_id")),
        "title": entry.get("title") or "",
        "image": entry.get("image") or "",
        "year": _int_or_none(entry.get("year")),
        "role": entry.get("role") or "",
        "departments": list(departments),
        "credit_type": entry.get("credit_type") or "",
        "vote_average": _float_or_none(entry.get("vote_average")),
        "vote_count": _int_or_none(entry.get("vote_count")),
        "popularity": _float_or_none(entry.get("popularity")),
        "item_id": item.id if item is not None else None,
        "genres": list(getattr(item, "genres", None) or []),
        "implied_genres": list(getattr(item, "implied_genres", None) or []),
        "watched": bool(entry.get("is_watched")),
        "watched_minutes": entry.get("watched_person_minutes"),
    }


class PersonDetailView(drf_views.APIView):
    """A person or author with their credits, marked with what the user watched.

    Sources with person pages: tmdb, tvdb, hardcover, openlibrary, comicvine
    and mangaupdates.
    """

    @extend_schema(
        operation_id="getPerson",
        responses={
            200: PersonDetailResponseSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="The source has no person pages.",
            ),
            404: OpenApiResponse(
                DetailErrorSerializer,
                description="The provider has no such person.",
            ),
            503: _PROVIDER_503,
        },
    )
    def get(self, request, source, person_id):
        """Return the profile, every credit and the user's watched totals."""
        # Provider failures reach api.exceptions: 404 for a person the
        # provider does not know, 503 provider_unavailable otherwise.
        with credentials.current_user_scope(request.user):
            page = people_data.build_person_page(request.user, source, person_id)
        if page is None:
            return Response(
                {"detail": "Person pages are not available for this source."},
                status=HTTP.BAD_REQUEST,
            )
        person = page["person"]
        payload = {
            "person": {
                "source": person["source"],
                "person_id": person["person_id"],
                "name": person["name"],
                "image": person["image"] or "",
                "biography": person["biography"] or "",
                "known_for_department": person["known_for_department"] or "",
                "birth_date": person["birth_date"],
                "death_date": person["death_date"],
                "place_of_birth": person["place_of_birth"] or "",
                "is_author": page["is_author"],
                "source_url": page["source_url"],
            },
            "credits": [_credit_payload(entry) for entry in page["filmography"]],
            "watched_credits": [
                _credit_payload(entry) for entry in page["watched_filmography"]
            ],
            "known_for": [_credit_payload(entry) for entry in page["known_for"]],
            "watched": {
                "movies": page["watched_movie_count"],
                "shows": page["watched_show_count"],
                "books": page["watched_book_count"],
                "plays": page["tracked_plays_count"],
                "minutes": page["tracked_minutes"],
            },
        }
        return Response(payload, status=HTTP.OK)


# --- /api/v1/studios/{source}/{studio_id}/ -----------------------------------


class StudioTitleSerializer(serializers.Serializer):
    """One credited title of a studio."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField()
    image = serializers.CharField()
    year = serializers.IntegerField(allow_null=True)
    item_id = serializers.IntegerField(
        allow_null=True,
        help_text="Floppy's item id when the title is known to this server.",
    )


class StudioDetailResponseSerializer(serializers.Serializer):
    """A studio page."""

    source = serializers.CharField()
    studio_id = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(
        allow_blank=True,
        help_text="From IGDB; empty for studios known only from local credits.",
    )
    source_url = serializers.CharField(allow_blank=True)
    founded = serializers.CharField(allow_null=True)
    developed_count = serializers.IntegerField(allow_null=True)
    published_count = serializers.IntegerField(allow_null=True)
    titles = StudioTitleSerializer(
        many=True,
        help_text="Credited titles, newest first, then by title.",
    )


class StudioDetailView(drf_views.APIView):
    """A studio or company with its credited titles.

    Studios come from the credits Floppy stored; IGDB studios add a profile
    and their full game list.
    """

    @extend_schema(
        operation_id="getStudio",
        responses={
            200: StudioDetailResponseSerializer,
            404: OpenApiResponse(
                DetailErrorSerializer,
                description="No studio with this id is known to this server.",
            ),
            503: _PROVIDER_503,
        },
    )
    def get(self, request, source, studio_id):
        """Return the studio's profile and titles."""
        # Unknown studios raise Http404; IGDB failures reach api.exceptions.
        with credentials.current_user_scope(request.user):
            page = people_data.build_studio_page(source, studio_id)
        studio = page["studio"]
        has_profile = page["studio_description"] != people_data.LOCAL_STUDIO_DESCRIPTION
        payload = {
            "source": source,
            "studio_id": str(studio_id),
            "name": studio.name,
            "description": page["studio_description"] if has_profile else "",
            "source_url": page["studio_source_url"] or "",
            "founded": (
                str(page["studio_founded"]) if page["studio_founded"] else None
            ),
            "developed_count": _int_or_none(page["studio_developed_count"]),
            "published_count": _int_or_none(page["studio_published_count"]),
            "titles": [
                {
                    "media_type": entry.get("media_type") or "",
                    "source": entry.get("source") or source,
                    "media_id": str(entry.get("media_id")),
                    "title": entry.get("title") or "",
                    "image": entry.get("image") or "",
                    "year": _int_or_none(entry.get("year")),
                    "item_id": (
                        entry["tracked_item"].id
                        if entry.get("tracked_item") is not None
                        else None
                    ),
                }
                for entry in page["credited_titles"]
            ],
        }
        return Response(payload, status=HTTP.OK)
