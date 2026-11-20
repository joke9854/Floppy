"""The detail page screen for the new web app (v2 P4-C1).

Three reads of the Django movie and show page, built by the page's own
builders (see `api.details_screen`): the hero (the shell phase, caches only),
the sections below it (the secondary phase) and one season's episodes (what
a season pill or "Show more" loads). Other media types answer 400, and the
web keeps their Django page.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.providers import credentials

from .contract_serializers import DetailErrorSerializer
from .details_screen import (
    DETAIL_SCREEN_TYPES,
    DetailSeasonSerializer,
    DetailSectionsSerializer,
    DetailShellSerializer,
    DetailTrailersSerializer,
    build_detail_screen,
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
