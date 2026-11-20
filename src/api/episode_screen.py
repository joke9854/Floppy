"""The web episode page's data (v2 P4-C3): the Django episode page, as JSON.

`app.views.build_episode_context` is the page's own builder, so this shows
the same episode, season strip, guest stars and crew as /details/.../episode/N;
values follow the CineTrack templates (`episode_details.html` with ct_shell,
`ct/episode_sections.html`).
"""

from __future__ import annotations

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags
from rest_framework import serializers

from app.models import MediaTypes
from app.templatetags import app_tags
from users.templatetags import user_tags

from .details_screen import (
    DetailPersonSerializer,
    DetailScoreSerializer,
    _person,
    _text,
)
from .home_screen import HomeCheckTargetSerializer


def _episode_url(context, number) -> str | None:
    name = (
        "anime_episode_details"
        if context.get("parent_media_type") == MediaTypes.ANIME.value
        else "episode_details"
    )
    try:
        return reverse(
            name,
            kwargs={
                "source": context["source"],
                "media_id": context["media_id"],
                "title": app_tags.slug(context.get("show_title") or ""),
                "season_number": context["season_number"],
                "episode_number": number,
            },
        )
    except NoReverseMatch:
        return None


def _show_url(context) -> str | None:
    media_type = (
        MediaTypes.ANIME.value
        if context.get("parent_media_type") == MediaTypes.ANIME.value
        else MediaTypes.TV.value
    )
    try:
        return reverse(
            "media_details",
            kwargs={
                "source": context["source"],
                "media_type": media_type,
                "media_id": context["media_id"],
                "title": app_tags.slug(context.get("show_title") or ""),
            },
        )
    except NoReverseMatch:
        return None


def _scores(context) -> list[dict]:
    """Return the score chips (TMDB's episode score, IMDb's), as the page."""
    metadata = context.get("episode_metadata") or {}
    scores = []
    if metadata.get("score_count") and metadata.get("score") is not None:
        scores.append(
            {
                "key": "provider",
                "label": "The Movie Database",
                "short": "TMDB",
                "rating": _text(metadata.get("score")),
                "count": metadata.get("score_count"),
            }
        )
    imdb = context.get("imdb_score") or {}
    if imdb.get("rating") is not None:
        scores.append(
            {
                "key": "imdb",
                "label": "IMDb",
                "short": "IMDb",
                "rating": _text(imdb.get("rating")),
                "count": imdb.get("rating_count"),
            }
        )
    return scores


def build_episode_screen(
    request, source, media_id, season_number, episode_number
) -> dict | None:
    """Return the episode page for the web, or None for an episode it cannot find."""
    from app.views import build_episode_context

    # The title is only the URL slug; the links below use the show's own.
    context = build_episode_context(
        request, source, media_id, "show", season_number, episode_number
    )
    user = request.user
    episode = context.get("episode") or {}
    if not episode and not context.get("episode_metadata"):
        return None
    public = bool(context.get("public_view"))
    history = episode.get("history") or []
    hide_spoilers = bool(getattr(user, "obfuscate_episodes", False)) and not history
    image = episode.get("image") or settings.IMG_NONE
    air_date = episode.get("air_date")
    overview = strip_tags(_text(episode.get("overview"))).strip()
    item = episode.get("item")
    metadata = context.get("episode_metadata") or {}
    current = context.get("current_instance")
    season_media = {"source": source, "media_id": media_id}
    strip = []
    for row in context.get("episodes") or []:
        number = row.get("episode_number")
        strip.append(
            {
                "episode_number": number,
                "display_number": _text(row.get("display_episode_number") or number),
                "title": _text(row.get("title")),
                "still": app_tags.image_url(
                    app_tags.tmdb_size(row.get("image") or settings.IMG_NONE, "w300")
                ),
                "watched": bool(row.get("history")),
                "blurred": bool(getattr(user, "obfuscate_episodes", False))
                and not row.get("history"),
                "air_date": _text(user_tags.user_date_format(row["air_date"], user))
                if row.get("air_date")
                else "",
                "current": number == episode_number,
                "url": _episode_url(context, number),
            }
        )
    return {
        "show_title": _text(context.get("show_title")),
        "show_url": _show_url(context),
        "season_title": _text(context.get("season_title")),
        "season_url": f"{_show_url(context)}?season={season_number}"
        if _show_url(context)
        else None,
        "page_url": _episode_url(context, episode_number),
        "title": _text(context.get("episode_title")),
        "season_number": season_number,
        "episode_number": episode_number,
        "display_number": _text(episode.get("display_episode_number") or episode_number),
        "still": app_tags.image_url(image),
        "blurred": hide_spoilers and not public,
        "backdrop": app_tags.ct_detail_backdrop(context.get("season_metadata") or {}, allow_network=False),
        "runtime": _text(episode.get("runtime")) or None,
        "aired": _text(user_tags.user_date_format(air_date, user)) if air_date else None,
        "scores": _scores(context),
        "watched": bool(history),
        "check": {
            "source": source,
            "media_id": str(media_id),
            "season_number": season_number,
            "episode_number": episode_number,
            "library_media_type": getattr(item, "library_media_type", None),
        }
        if episode and not public
        else None,
        "overview": overview,
        "overview_hidden": bool(overview)
        and bool(getattr(user, "hide_episode_overviews", False))
        and not history,
        "previous_url": _episode_url(context, context["prev_episode_number"])
        if context.get("prev_episode_number")
        else None,
        "next_url": _episode_url(context, context["next_episode_number"])
        if context.get("next_episode_number")
        else None,
        "season_watched": getattr(current, "completed_episode_count", None)
        if current is not None
        else None,
        "episodes": strip if len(strip) > 1 else [],
        "guest_stars": [_person(person, season_media) for person in (metadata.get("cast") or [])[:20]]
        if source == "tmdb"
        else [],
        "crew": [
            {
                "label": _text(person.get("role") or person.get("department")),
                "name": _text(person.get("name")),
                "url": _person(person, season_media)["url"],
            }
            for person in (metadata.get("crew") or [])[:9]
        ]
        if source == "tmdb"
        else [],
        "track_time": settings.TRACK_TIME,
    }


class EpisodeStripSerializer(serializers.Serializer):
    """An episode in the season strip."""

    episode_number = serializers.IntegerField(allow_null=True)
    display_number = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    still = serializers.CharField()
    watched = serializers.BooleanField()
    blurred = serializers.BooleanField()
    air_date = serializers.CharField(allow_blank=True)
    current = serializers.BooleanField()
    url = serializers.CharField(allow_null=True)


class EpisodeCrewSerializer(serializers.Serializer):
    """A key crew credit, for the Information grid."""

    label = serializers.CharField(allow_blank=True)
    name = serializers.CharField()
    url = serializers.CharField(allow_null=True)


class EpisodeScreenSerializer(serializers.Serializer):
    """The episode page."""

    show_title = serializers.CharField()
    show_url = serializers.CharField(allow_null=True)
    season_title = serializers.CharField()
    season_url = serializers.CharField(allow_null=True)
    page_url = serializers.CharField(allow_null=True, help_text="The Django episode page.")
    title = serializers.CharField()
    season_number = serializers.IntegerField()
    episode_number = serializers.IntegerField()
    display_number = serializers.CharField()
    still = serializers.CharField()
    blurred = serializers.BooleanField(help_text="Hide the still until watched (user setting).")
    backdrop = serializers.CharField(allow_null=True)
    runtime = serializers.CharField(allow_null=True)
    aired = serializers.CharField(allow_null=True)
    scores = DetailScoreSerializer(many=True)
    watched = serializers.BooleanField()
    check = HomeCheckTargetSerializer(allow_null=True)
    overview = serializers.CharField(allow_blank=True)
    overview_hidden = serializers.BooleanField(
        help_text="Hide the overview until watched (user setting)."
    )
    previous_url = serializers.CharField(allow_null=True)
    next_url = serializers.CharField(allow_null=True)
    season_watched = serializers.IntegerField(allow_null=True)
    episodes = EpisodeStripSerializer(many=True)
    guest_stars = DetailPersonSerializer(many=True)
    crew = EpisodeCrewSerializer(many=True)
    track_time = serializers.BooleanField()
