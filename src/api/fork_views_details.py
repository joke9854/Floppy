"""The detail page screen for the new web app (v2 P4-C1).

Three reads of the Django movie and show page, built by the page's own
builders (see `api.details_screen`): the hero (the shell phase, caches only),
the sections below it (the secondary phase) and one season's episodes (what
a season pill or "Show more" loads). Other media types answer 400, and the
web keeps their Django page.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.http import HttpResponse
from drf_spectacular.utils import (
    OpenApiParameter,
    PolymorphicProxySerializer,
    extend_schema,
)
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import MediaTypes
from app.providers import credentials

from .calendar_screen import CalendarScreenSerializer, build_calendar_screen
from .contract_serializers import DetailErrorSerializer
from .details_media_screen import (
    PODCAST_SOURCES,
    AlbumScreenSerializer,
    ArtistScreenSerializer,
    PodcastEpisodesPageSerializer,
    PodcastScreenSerializer,
    build_album_screen,
    build_artist_screen,
    build_podcast_screen,
)
from .details_screen import (
    DETAIL_SCREEN_TYPES,
    DetailSeasonSerializer,
    DetailSectionsSerializer,
    DetailShellSerializer,
    DetailTrailersSerializer,
    build_detail_screen,
)
from .discover_screen import DiscoverScreenSerializer, build_discover_screen
from .episode_screen import EpisodeScreenSerializer, build_episode_screen
from .history_screen import HistoryScreenSerializer, build_history_screen
from .list_detail_screen import ListPageSerializer, build_list_detail_screen
from .lists_screen import ListsScreenSerializer, build_lists_screen
from .person_screen import PersonScreenSerializer, build_person_screen
from .settings_screen import SettingsScreenSerializer, build_settings_screen
from .statistics_screen import StatisticsScreenSerializer, build_statistics_screen
from .statistics_talent_screen import StatisticsTalentSerializer, build_talent_screen
from .track_screen import (
    TRACK_SCREEN_TYPES,
    TRACKER_SCREEN_TYPES,
    ActivityScreenSerializer,
    TrackScreenSerializer,
    build_activity_screen,
    build_track_screen,
    build_tracker_screen,
    tracker_context,
)

_NOTE = (
    " Built by the Django page's own builder, so it shows what the page shows. "
    "Like the page, the read can store metadata it resolves, so integration "
    "tokens cannot call it."
)
_UNSUPPORTED = {"detail": "This media type has no web detail page yet."}
_REDIRECTED = {"detail": "The Django page answers this title with a redirect."}


def _screen(request, media_type, source, media_id, part, serializer):
    if media_type not in DETAIL_SCREEN_TYPES:
        return Response(_UNSUPPORTED, status=HTTP.BAD_REQUEST)
    with credentials.current_user_scope(request.user):
        data = build_detail_screen(request._request, media_type, source, media_id, part)
    if isinstance(data, HttpResponse):
        return Response(_REDIRECTED, status=HTTP.BAD_REQUEST)
    if data is None:
        return Response(
            {"detail": "This show has no such season."}, status=HTTP.NOT_FOUND
        )
    return Response(serializer(data).data, status=HTTP.OK)


# /api/v1/details/{media_type}/{source}/{media_id}/
class DetailShellView(drf_views.APIView):
    """The hero of a movie or show page: what the page paints first."""

    @extend_schema(
        operation_id="getDetailShell",
        description="The hero, read from caches only, so it never waits on a provider."
        + _NOTE,
        responses={200: DetailShellSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request, media_type, source, media_id):
        """Return the hero of the page."""
        return _screen(
            request, media_type, source, media_id, "shell", DetailShellSerializer
        )


# /api/v1/details/{media_type}/{source}/{media_id}/sections/
class DetailSectionsView(drf_views.APIView):
    """The sections below the hero of a movie or show page."""

    @extend_schema(
        operation_id="getDetailSections",
        description=(
            "Episodes (a show's season on screen), Your Plays, related lists, cast, "
            "More Like This and Information, with a backdrop and Watch on the "
            "hero lacked. It may fetch from the provider." + _NOTE
        ),
        parameters=[
            OpenApiParameter(
                "season",
                int,
                description="The season on screen; else the next episode's, else the first.",
            ),
            OpenApiParameter(
                "episode_page",
                int,
                description="A comic volume's page of issues (`issues_more.page`).",
            ),
        ],
        responses={200: DetailSectionsSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request, media_type, source, media_id):
        """Return the sections of the page."""
        return _screen(
            request, media_type, source, media_id, "secondary", DetailSectionsSerializer
        )


# /api/v1/details/tv/{source}/{media_id}/season/?season=N
class DetailSeasonView(drf_views.APIView):
    """One season of a show page's episode list."""

    @extend_schema(
        operation_id="getDetailSeason",
        description="One season's episodes, as a season pill or Show more loads them."
        + _NOTE,
        parameters=[
            OpenApiParameter("season", int, required=True),
            OpenApiParameter(
                "episode_page", int, description="From `load_more.querystring`."
            ),
        ],
        responses={
            200: DetailSeasonSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, source, media_id):
        """Return one season's episodes."""
        if not request.GET.get("season", "").isdigit():
            return Response({"detail": "season is required."}, status=HTTP.BAD_REQUEST)
        return _screen(
            request, "tv", source, media_id, "season", DetailSeasonSerializer
        )


# /api/v1/details/anime/{source}/{media_id}/season/?season=N
class DetailAnimeSeasonView(drf_views.APIView):
    """One season of an anime page's episode list (the anime bucket's rows)."""

    @extend_schema(
        operation_id="getDetailAnimeSeason",
        description="One season's episodes of an anime filed as a series: the rows "
        "read the anime bucket, and the links open the anime episode pages." + _NOTE,
        parameters=[
            OpenApiParameter("season", int, required=True),
            OpenApiParameter(
                "episode_page", int, description="From `load_more.querystring`."
            ),
        ],
        responses={
            200: DetailSeasonSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, source, media_id):
        """Return one season's episodes."""
        if not request.GET.get("season", "").isdigit():
            return Response({"detail": "season is required."}, status=HTTP.BAD_REQUEST)
        return _screen(
            request, "anime", source, media_id, "season", DetailSeasonSerializer
        )


# /api/v1/details/{media_type}/{source}/{media_id}/trailers/
class DetailTrailersView(drf_views.APIView):
    """A movie's or show's trailers and teasers (the page's ?fragment=trailers)."""

    @extend_schema(
        operation_id="getDetailTrailers",
        description=(
            "Every trailer and teaser, a show's own first, then its newest seasons'. "
            "TMDB titles only; an empty list otherwise or while TMDB is unreachable."
            + _NOTE
        ),
        responses={200: DetailTrailersSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request, media_type, source, media_id):
        """Return the trailers."""
        return _screen(
            request, media_type, source, media_id, "trailers", DetailTrailersSerializer
        )


def _media_screen(request, builder, serializer, *args):
    """Run a music or podcast page builder: 400 for the page's redirect, 404 for none."""
    with credentials.current_user_scope(request.user):
        data = builder(request._request, *args)
    if isinstance(data, HttpResponse):
        return Response(_REDIRECTED, status=HTTP.BAD_REQUEST)
    if data is None:
        return Response({"detail": "Not found."}, status=HTTP.NOT_FOUND)
    return Response(serializer(data).data, status=HTTP.OK)


# /api/v1/details/music/artist/{artist_id}/
class MusicArtistScreenView(drf_views.APIView):
    """A music artist page for the new web app (v2 P4-L2)."""

    @extend_schema(
        operation_id="getMusicArtistScreen",
        description=(
            "The artist page: bio, details, members, the discography with your play "
            "counts and scores, built by the Django page's own builder. 400 when "
            "the page answers with a redirect (a merged artist); the web opens the "
            "Django page." + _NOTE
        ),
        responses={
            200: ArtistScreenSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, artist_id):
        """Return the artist page."""
        return _media_screen(
            request, build_artist_screen, ArtistScreenSerializer, int(artist_id)
        )


# /api/v1/details/music/artist/{artist_id}/album/{album_id}/
class MusicAlbumScreenView(drf_views.APIView):
    """A music album page for the new web app (v2 P4-L2)."""

    @extend_schema(
        operation_id="getMusicAlbumScreen",
        description=(
            "The album page: details, genres and every track with the exact "
            "instants of your plays (newest first), built by the Django page's own "
            "builder. 400 when the page answers with a redirect (an album that "
            "canonicalizes elsewhere, or another artist's URL)." + _NOTE
        ),
        responses={
            200: AlbumScreenSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, artist_id, album_id):
        """Return the album page."""
        return _media_screen(
            request,
            build_album_screen,
            AlbumScreenSerializer,
            int(artist_id),
            int(album_id),
        )


# /api/v1/details/podcast/{source}/{podcast_uuid}/
class PodcastScreenView(drf_views.APIView):
    """A podcast show page for the new web app (v2 P4-L2)."""

    @extend_schema(
        operation_id="getPodcastScreen",
        description=(
            "The show page with its first 20 episodes and your plays of each. The "
            "first read refreshes the feed, as the page does. With `episode_page` "
            "above 1 it answers only that page of episodes (a "
            "`PodcastEpisodesPage`) and never refreshes the feed. 400 for another "
            "source, or when the page answers with a redirect (an iTunes id)." + _NOTE
        ),
        parameters=[
            OpenApiParameter(
                "episode_page",
                int,
                description="Page of 20 episodes (`episodes.next_page`); invalid is 1.",
            ),
        ],
        responses={
            200: PolymorphicProxySerializer(
                component_name="PodcastScreenOrEpisodesPage",
                serializers=[PodcastScreenSerializer, PodcastEpisodesPageSerializer],
                resource_type_field_name=None,
            ),
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def get(self, request, source, podcast_uuid):
        """Return the show page, or one page of its episodes."""
        if source not in PODCAST_SOURCES:
            return Response(
                {"detail": "Not a podcast source."}, status=HTTP.BAD_REQUEST
            )
        raw = request.query_params.get("episode_page", "")
        page = int(raw) if raw.isdigit() and int(raw) >= 1 else 1
        serializer = PodcastScreenSerializer if page == 1 else PodcastEpisodesPageSerializer
        return _media_screen(
            request, build_podcast_screen, serializer, source, podcast_uuid, page
        )


# /api/v1/details/person/{source}/{person_id}/
class PersonScreenView(drf_views.APIView):
    """A person or author page for the new web app (v2 P4-C3)."""

    @extend_schema(
        operation_id="getPersonScreen",
        description=(
            "The person page: the person, your numbers with them, the titles you "
            "have watched, Known For and the filmography, built by the Django "
            "page's own builder. 400 for a source without person pages." + _NOTE
        ),
        responses={200: PersonScreenSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request, source, person_id):
        """Return the person page."""
        with credentials.current_user_scope(request.user):
            data = build_person_screen(request._request, source, person_id)
        if isinstance(data, HttpResponse):
            return Response(
                {"detail": "Person pages are not available for this source."},
                status=HTTP.BAD_REQUEST,
            )
        return Response(PersonScreenSerializer(data).data, status=HTTP.OK)


# /api/v1/details/episode/{source}/{media_id}/{season_number}/{episode_number}/
class EpisodeScreenView(drf_views.APIView):
    """An episode page for the new web app (v2 P4-C3)."""

    @extend_schema(
        operation_id="getEpisodeScreen",
        description=(
            "The episode page: the episode, the season strip, guest stars and key "
            "crew, built by the Django page's own builder." + _NOTE
        ),
        parameters=[
            OpenApiParameter(
                "parent",
                str,
                description="`anime` for an anime filed as a series (its own bucket).",
            )
        ],
        responses={
            200: EpisodeScreenSerializer,
            404: DetailErrorSerializer,
            503: DetailErrorSerializer,
        },
    )
    def get(self, request, source, media_id, season_number, episode_number):
        """Return the episode page."""
        parent = "anime" if request.GET.get("parent") == "anime" else None
        from app.providers import services

        try:
            with credentials.current_user_scope(request.user):
                data = build_episode_screen(
                    request._request,
                    source,
                    media_id,
                    int(season_number),
                    int(episode_number),
                    parent,
                )
        except services.ProviderAPIError:
            return Response(
                {"detail": "The provider is not answering. Try again later."},
                status=HTTP.SERVICE_UNAVAILABLE,
            )
        if data is None:
            return Response({"detail": "No such episode."}, status=HTTP.NOT_FOUND)
        return Response(EpisodeScreenSerializer(data).data, status=HTTP.OK)


# /api/v1/track/{media_type}/{source}/{media_id}/
class CalendarScreenView(drf_views.APIView):
    """The Calendar page for the web app (v2 P4-F)."""

    @extend_schema(
        operation_id="getCalendarScreen",
        description=(
            "The Django Calendar page's month (`month`, `year`): releases by local "
            "day as the page writes them, the month grid in the user's week start, "
            "the filter's types and statuses, and the iCal export options. `view` "
            "(grid or list) saves the user's layout, as on the page." + _NOTE
        ),
        responses={200: CalendarScreenSerializer},
    )
    def get(self, request):
        """Return the calendar screen."""
        data = build_calendar_screen(request._request)
        return Response(CalendarScreenSerializer(data).data, status=HTTP.OK)


class ListPageView(drf_views.APIView):
    """A manual list's page for the web app (v2 P4-I2)."""

    @extend_schema(
        operation_id="getListPage",
        description=(
            "The Django list page for `reference` (id or custom URL) with its own "
            "query: `q`, repeated `type` and `status`, `sort` and `direction`, "
            "`layout` (grid, table) and `page` (16 items); sort, statuses and "
            "layout are saved as the user's, as on the page. Cards and table "
            "cells match the Library's. A smart list adds `smart` (its saved rules, "
            "summary and builder options). A list the user cannot edit, or a "
            "missing one, answers `handled: false` and its Django page." + _NOTE
        ),
        parameters=[
            OpenApiParameter("q", str, required=False),
            OpenApiParameter("type", str, many=True, required=False),
            OpenApiParameter("status", str, many=True, required=False),
            OpenApiParameter("sort", str, required=False),
            OpenApiParameter("direction", str, required=False),
            OpenApiParameter("layout", str, required=False),
            OpenApiParameter("page", int, required=False),
        ],
        responses={200: ListPageSerializer},
    )
    def get(self, request, reference):
        """Return the list page."""
        data = build_list_detail_screen(request._request, reference)
        return Response(ListPageSerializer(data).data, status=HTTP.OK)


class SettingsScreenView(drf_views.APIView):
    """A settings page for the web app (v2 P4-J)."""

    @extend_schema(
        operation_id="getSettingsScreen",
        description=(
            "The settings nav and one page (`account`, `appearance`, "
            "`notifications`, `sidebar`, `about`), read as the Django page reads "
            "it. Any other page answers `handled: false` with its Django URL. "
            "The web saves through the Django views' forms, which answer JSON "
            "for `Accept: application/json`." + _NOTE
        ),
        responses={200: SettingsScreenSerializer},
    )
    def get(self, request, page):
        """Return the settings page."""
        data = build_settings_screen(request._request, page)
        return Response(SettingsScreenSerializer(data).data, status=HTTP.OK)


class ListsScreenView(drf_views.APIView):
    """The Lists index for the web app (v2 P4-I)."""

    @extend_schema(
        operation_id="getListsScreen",
        description=(
            "The Django Lists page for `scope` (mine, shared), `q`, `media_type`, "
            "`sort` and `direction` (saved as the user's list sort, as on the page) "
            "and `page` (20 lists): counts, toolbar options, cards with their "
            "four-poster covers, and where the page's actions post." + _NOTE
        ),
        parameters=[
            OpenApiParameter("scope", str, required=False),
            OpenApiParameter("q", str, required=False),
            OpenApiParameter("media_type", str, required=False),
            OpenApiParameter("sort", str, required=False),
            OpenApiParameter("direction", str, required=False),
            OpenApiParameter("page", int, required=False),
        ],
        responses={200: ListsScreenSerializer},
    )
    def get(self, request):
        """Return the lists screen."""
        data = build_lists_screen(request._request)
        return Response(ListsScreenSerializer(data).data, status=HTTP.OK)


class StatisticsScreenView(drf_views.APIView):
    """The Statistics page for the web app (v2 P4-H)."""

    @extend_schema(
        operation_id="getStatisticsScreen",
        description=(
            "The Django Statistics page for the page's own query: `start-date` and "
            "`end-date` (YYYY-MM-DD, or `all` for All Time; without them the user's "
            "default range) and `compare` (previous_period, last_year, none). A "
            "predefined range is saved as the user's default, as on the page. H1: "
            "the controls, every type's summary and highlights, the Activity card, "
            "Activity History and Played Hours by Media Type, the preferences." + _NOTE
        ),
        parameters=[
            OpenApiParameter("start-date", str, required=False),
            OpenApiParameter("end-date", str, required=False),
            OpenApiParameter("compare", str, required=False),
        ],
        responses={200: StatisticsScreenSerializer},
    )
    def get(self, request):
        """Return the statistics screen."""
        data = build_statistics_screen(request._request)
        return Response(StatisticsScreenSerializer(data).data, status=HTTP.OK)


class StatisticsTalentView(drf_views.APIView):
    """The Statistics page's talent section for the web app (v2 P4-H3)."""

    @extend_schema(
        operation_id="getStatisticsTalent",
        description=(
            "The talent fragment's own context for `range_name` (a preset) or "
            "`start-date`/`end-date`, and `compare`: the Featured Repeat Player with "
            "their titles, Role Leaders, Studio Footprint, Top Genres and Era "
            "Spotlight, sorted by the user's saved sorts. `media_type` (tv, movie, "
            "anime, game) re-aggregates the leaders, player and studios for it; "
            "`person_source` and `person_id` feature that person." + _NOTE
        ),
        parameters=[
            OpenApiParameter("range_name", str, required=False),
            OpenApiParameter("start-date", str, required=False),
            OpenApiParameter("end-date", str, required=False),
            OpenApiParameter("compare", str, required=False),
            OpenApiParameter("media_type", str, required=False),
            OpenApiParameter("person_source", str, required=False),
            OpenApiParameter("person_id", str, required=False),
        ],
        responses={200: StatisticsTalentSerializer},
    )
    def get(self, request):
        """Return the talent section."""
        data = build_talent_screen(request._request)
        return Response(StatisticsTalentSerializer(data).data, status=HTTP.OK)


class DiscoverScreenView(drf_views.APIView):
    """The Discover page for the web app (v2 P4-G)."""

    @extend_schema(
        operation_id="getDiscoverScreen",
        description=(
            "The Django Discover page for `media_type` (saved as the user's last "
            "Discover type, as on the page; `hidden` is the Hidden view) and "
            "`show_more`: the type tabs, the hero, the rows with each card's "
            "quick-action fields for `/discover/action`, and the hidden items. "
            "`loading` is true while the rows rebuild in the background." + _NOTE
        ),
        parameters=[
            OpenApiParameter("media_type", str, required=False),
            OpenApiParameter("show_more", str, required=False),
        ],
        responses={200: DiscoverScreenSerializer},
    )
    def get(self, request):
        """Return the discover screen."""
        data = build_discover_screen(request._request)
        return Response(DiscoverScreenSerializer(data).data, status=HTTP.OK)


class HistoryScreenView(drf_views.APIView):
    """The History page for the web app (v2 P4-E)."""

    @extend_schema(
        operation_id="getHistoryScreen",
        description=(
            "The Django History page's days and rows: the month view (`year`, `m`) "
            "from the history cache, or a page (`page`) of a filtered view: "
            "`media_type` (comma-separated), `start-date`/`end-date`, "
            "`history_mode=release`, `month`+`day` (on this day), genre, title "
            "and person filters, `logging_style`. Each row as the page writes it, "
            "with the track dialog target for Edit tracking." + _NOTE
        ),
        responses={200: HistoryScreenSerializer},
    )
    def get(self, request):
        """Return the history screen."""
        data = build_history_screen(request._request)
        return Response(HistoryScreenSerializer(data).data, status=HTTP.OK)


class ActivityScreenView(drf_views.APIView):
    """A title's Activity History for the web app (v2 P4-D7)."""

    @extend_schema(
        operation_id="getActivityScreen",
        description=(
            "The Django Activity History dialog's timeline for a title or an "
            "episode: each entry's date, its changes, the play it describes "
            "(open the track dialog with `instance_id` to edit it) and where to "
            "DELETE it." + _NOTE
        ),
        parameters=[
            OpenApiParameter("season_number", int, description="Seasons and episodes."),
            OpenApiParameter("episode_number", int, description="Episodes."),
        ],
        responses={200: ActivityScreenSerializer, 400: DetailErrorSerializer},
    )
    def get(self, request, media_type, source, media_id):
        """Return the activity history."""
        if media_type not in TRACK_SCREEN_TYPES:
            return Response(
                {"detail": "This media type has no web activity history yet."},
                status=HTTP.BAD_REQUEST,
            )
        numbers = {}
        for name in ("season_number", "episode_number"):
            value = request.query_params.get(name)
            if value is not None:
                if not value.isdigit():
                    return Response({"detail": f"{name} must be a number."}, status=HTTP.BAD_REQUEST)
                numbers[name] = int(value)
        data = build_activity_screen(request._request, media_type, source, media_id, **numbers)
        return Response(ActivityScreenSerializer(data).data, status=HTTP.OK)


class TrackScreenView(drf_views.APIView):
    """The track dialog's General tab for the new web app (v2 P4-D1)."""

    @extend_schema(
        operation_id="getTrackScreen",
        description=(
            "The Django track dialog's form for a title: its fields in order with "
            "their values, choices and limits, the date shortcut, and where to "
            "post. Post the fields back to `save_url` (or `delete_url`, "
            "`rewatch.url`) as a form with `Accept: application/json`. The types "
            "the page's standard dialog edits (movies, shows, seasons, episodes, "
            "anime, manga, games, books, comics, comic issues, board games; "
            "`anime` also opens a TMDB show filed as anime, like the page). Music "
            "artists and albums as `artist|album/music/{id}`, podcast shows as "
            "`podcast/{source}/{podcast_uuid}`: the page's shared tracker dialog. "
            "400 for anything else (songs and podcast episodes keep the page's "
            "own dialog)." + _NOTE
        ),
        parameters=[
            OpenApiParameter("season_number", int, description="Seasons and episodes."),
            OpenApiParameter("episode_number", int, description="Episodes."),
            OpenApiParameter("instance_id", int, description="A specific play to edit."),
        ],
        responses={
            200: TrackScreenSerializer,
            400: DetailErrorSerializer,
            503: DetailErrorSerializer,
        },
    )
    def get(self, request, media_type, source, media_id):
        """Return the track form."""
        from app.providers import services

        if media_type in TRACKER_SCREEN_TYPES:
            with credentials.current_user_scope(request.user):
                context = tracker_context(request._request, media_type, source, media_id)
                if context is None:
                    return Response(
                        {"detail": "This title has no web track dialog yet."},
                        status=HTTP.BAD_REQUEST,
                    )
                data = build_tracker_screen(request._request, media_type, context)
            return Response(TrackScreenSerializer(data).data, status=HTTP.OK)
        if media_type not in TRACK_SCREEN_TYPES:
            return Response(
                {"detail": "This media type has no web track dialog yet."},
                status=HTTP.BAD_REQUEST,
            )

        def number(name):
            raw = request.query_params.get(name)
            return int(raw) if raw and raw.isdigit() else None

        season_number = number("season_number")
        episode_number = number("episode_number")
        if media_type in (MediaTypes.SEASON.value, MediaTypes.EPISODE.value) and season_number is None:
            return Response({"detail": "season_number is required."}, status=HTTP.BAD_REQUEST)
        if media_type == MediaTypes.EPISODE.value and episode_number is None:
            return Response({"detail": "episode_number is required."}, status=HTTP.BAD_REQUEST)
        try:
            with credentials.current_user_scope(request.user):
                data = build_track_screen(
                    request._request, media_type, source, media_id, season_number, episode_number
                )
        except services.ProviderAPIError:
            return Response(
                {"detail": "The provider is not answering. Try again later."},
                status=HTTP.SERVICE_UNAVAILABLE,
            )
        return Response(TrackScreenSerializer(data).data, status=HTTP.OK)
