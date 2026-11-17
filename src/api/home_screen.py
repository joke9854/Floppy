"""The v2 Home screen's data for the new web app (v2 P4-A).

`GET /api/v1/home/` keeps its client shape (groups of rows of media records)
and loses what the screen shows: Airing's day, time and tags, the catch-up
counts and the In Progress card details. This builds the screen's own shape
from the same cached sections (`app.home_sections.build_home_sections`), with
every display value worked out by the helpers the Django templates use, so the
two Homes say the same thing.

Images are the proxied, sized URLs the templates render. Backdrops are read
from the cache only: Home never waits on a provider.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from app import helpers
from app.models import MediaTypes, Status
from app.templatetags import app_tags


def _poster(item, size: str, srcset_sizes: str = "") -> tuple[str, str]:
    """Return a card's proxied poster URL and its srcset ("" when none)."""
    image = app_tags.ct_poster(item) or settings.IMG_NONE
    url = app_tags.image_url(app_tags.tmdb_size(image, size))
    srcset = app_tags.tmdb_srcset(image, srcset_sizes) if srcset_sizes else ""
    return url, srcset


def _release_label(item, event) -> str:
    """Return "S2 E5", the event's own number, or the media type's name."""
    if item.season_number is not None and event.content_number:
        return f"S{item.season_number} E{event.content_number}"
    if event.readable_content_number:
        return str(event.readable_content_number)
    return str(app_tags.media_type_readable(item.media_type))


def _year(item) -> int | None:
    release = getattr(item, "release_datetime", None)
    return release.year if release else None


def _in_progress_card(entry, user) -> dict:
    """One In Progress card, as ct/progress_card.html renders it."""
    item, media = entry.item, entry.media
    next_episode = app_tags.ct_next_episode(entry)
    url = app_tags.ct_episode_url(
        item, entry.target_season_number, entry.target_episode_number
    )
    if not url and next_episode:
        url = app_tags.next_episode_url(item, media)
    poster, srcset = _poster(
        getattr(media, "card_image_override", None) or item, "w342", "w185,w342,w500"
    )
    backdrop = app_tags.ct_card_backdrop(item)
    percent = entry.resume_percent
    if percent is None:
        percent = app_tags.safe_attr(media, "progress_percentage") or 0
    remaining = entry.remaining_seconds or None
    # The template names time or episodes left only beside an episode, and
    # only when the resume time left is unknown.
    time_left = episodes_left = None
    if next_episode and not remaining:
        time_left = getattr(media, "time_left_display", None) or None
        if not time_left:
            episodes_left = getattr(media, "episodes_left", None) or None
    episode = None
    check = None
    if next_episode:
        episode = {
            "season_number": next_episode["season_number"],
            "episode_number": next_episode["episode_number"],
            "title": next_episode.get("episode_title") or None,
        }
        check = {
            "source": next_episode["source"],
            "media_id": str(next_episode["media_id"]),
            "season_number": next_episode["season_number"],
            "episode_number": next_episode["episode_number"],
            "library_media_type": next_episode.get("library_media_type") or None,
        }
    return {
        "key": item.id,
        "kind": entry.kind,
        "media_type": item.media_type,
        "title": app_tags.display_title(item, user),
        "url": url or app_tags.media_url(item),
        "poster": poster,
        "poster_srcset": srcset,
        "backdrop": (
            app_tags.image_url(app_tags.tmdb_size(backdrop, "w780")) if backdrop else None
        ),
        "progress_percent": int(percent),
        "episode": episode,
        "check": check,
        "time_left": time_left,
        "episodes_left": episodes_left,
        "remaining_seconds": remaining,
        "remaining_label": helpers.seconds_to_hm(remaining) if remaining else None,
        "is_rewatch": bool(entry.is_rewatch),
        "year": None if next_episode else _year(item),
    }


def _release(entry, user, poster_size: str) -> dict:
    """One Airing This Week or Coming Soon release."""
    event = entry.event
    item = event.item
    poster, srcset = _poster(item, poster_size, "w185,w342" if poster_size == "w342" else "")
    time = app_tags.user_event_time(event, user)
    return {
        "key": event.id,
        "title": item.title,
        "url": entry.url or app_tags.media_url(item),
        "poster": poster,
        "poster_srcset": srcset,
        "day": entry.day,
        "is_today": entry.is_today,
        # user_event_time reads "at 21:00"; the screen shows just the time.
        "time": time[3:] if time else None,
        "label": _release_label(item, event),
        "tag": entry.tag,
    }


def _recent_card(entry, user) -> dict:
    """One Recently Watched poster card, as ct/poster_card.html renders it."""
    item, media = entry.item, entry.media
    if item.media_type == MediaTypes.SEASON.value:
        title = app_tags.season_card_title(item)
    else:
        title = app_tags.display_title(item, user)
    poster, srcset = _poster(item, "w342", "w185,w342")
    progress = None
    if media is not None and user.progress_bar:
        status = getattr(media, "aggregated_status", None) or getattr(media, "status", None)
        max_progress = getattr(media, "max_progress", None)
        count = getattr(media, "progress", None)
        if (
            status in (Status.IN_PROGRESS.value, Status.PAUSED.value)
            and item.media_type != MediaTypes.MOVIE.value
            and max_progress
            and count
        ):
            percent = app_tags.safe_attr(media, "progress_percentage")
            if percent is None:
                percent = round(count * 100 / max_progress)
            progress = {"percent": int(percent), "paused": status == Status.PAUSED.value}
    if entry.subtitle_override:
        subtitle = str(app_tags.ct_relative_day(entry.subtitle_override))
    else:
        year = _year(item)
        subtitle = str(year) if year else ""
    return {
        "key": item.id,
        "media_type": item.media_type,
        "title": title,
        "url": app_tags.media_url(item),
        "poster": poster,
        "poster_srcset": srcset,
        "subtitle": subtitle,
        "status": getattr(media, "status", None) if media is not None else None,
        "progress": progress,
    }


def build_home_screen(user) -> dict:
    """Return the Home screen's summary and sections for ``user``."""
    from app import home_sections

    sections = home_sections.build_home_sections(user)
    app_tags.ct_prefetch_posters(sections["in_progress"], "item")
    airing = [entry for column in sections["airing"] for entry in column]
    return {
        "summary": {
            "catch_up": sections["catch_up"],
            "catch_up_shows": sections["catch_up_shows"],
            "airing_count": sections["airing_count"],
        },
        "in_progress": [_in_progress_card(entry, user) for entry in sections["in_progress"]],
        "in_progress_kinds": list(sections["in_progress_kinds"]),
        "airing": [_release(entry, user, "w154") for entry in airing],
        "recent": [_recent_card(entry, user) for entry in sections["recent"]],
        "coming_soon": [_release(entry, user, "w342") for entry in sections["coming_soon"]],
    }


class HomeEpisodeSerializer(serializers.Serializer):
    """The episode an In Progress card names."""

    season_number = serializers.IntegerField()
    episode_number = serializers.IntegerField()
    title = serializers.CharField(allow_null=True)


class HomeCheckTargetSerializer(serializers.Serializer):
    """What the card's check marks watched, in the episode ensure route's terms."""

    source = serializers.CharField()
    media_id = serializers.CharField()
    season_number = serializers.IntegerField()
    episode_number = serializers.IntegerField()
    library_media_type = serializers.CharField(allow_null=True)


class HomeInProgressCardSerializer(serializers.Serializer):
    """An In Progress card."""

    key = serializers.IntegerField(help_text="The item id; stable per card.")
    kind = serializers.ChoiceField(choices=("movie", "show"))
    media_type = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField(help_text="The Django page the card opens.")
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    backdrop = serializers.CharField(
        allow_null=True, help_text="Cached backdrop only; null shows the poster."
    )
    progress_percent = serializers.IntegerField()
    episode = HomeEpisodeSerializer(allow_null=True)
    check = HomeCheckTargetSerializer(
        allow_null=True, help_text="Null when there is no episode to mark."
    )
    time_left = serializers.CharField(allow_null=True)
    episodes_left = serializers.IntegerField(allow_null=True)
    remaining_seconds = serializers.IntegerField(allow_null=True)
    remaining_label = serializers.CharField(allow_null=True)
    is_rewatch = serializers.BooleanField()
    year = serializers.IntegerField(allow_null=True)


class HomeReleaseSerializer(serializers.Serializer):
    """A release in Airing This Week or Coming Soon."""

    key = serializers.IntegerField(help_text="The event id.")
    title = serializers.CharField()
    url = serializers.CharField()
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    day = serializers.DateField()
    is_today = serializers.BooleanField()
    time = serializers.CharField(
        allow_null=True, help_text="In the user's time format; null when unknown."
    )
    label = serializers.CharField(help_text='"S2 E5", or the release kind.')
    tag = serializers.ChoiceField(choices=("premiere", "finale"), allow_null=True)


class HomeCardProgressSerializer(serializers.Serializer):
    """The progress line on a poster card."""

    percent = serializers.IntegerField()
    paused = serializers.BooleanField()


class HomeRecentCardSerializer(serializers.Serializer):
    """A Recently Watched poster card."""

    key = serializers.IntegerField()
    media_type = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(
        allow_blank=True, help_text='When it was watched ("Today", "2 Nov"), else the year.'
    )
    status = serializers.CharField(allow_null=True)
    progress = HomeCardProgressSerializer(allow_null=True)


class HomeSummarySerializer(serializers.Serializer):
    """The header counts."""

    catch_up = serializers.IntegerField(help_text="Aired episodes not yet watched.")
    catch_up_shows = serializers.IntegerField()
    airing_count = serializers.IntegerField()


class HomeScreenSerializer(serializers.Serializer):
    """The Home screen: header counts and its four sections, in order."""

    summary = HomeSummarySerializer()
    in_progress = HomeInProgressCardSerializer(many=True)
    in_progress_kinds = serializers.ListField(child=serializers.CharField())
    airing = HomeReleaseSerializer(many=True)
    recent = HomeRecentCardSerializer(many=True)
    coming_soon = HomeReleaseSerializer(many=True)
