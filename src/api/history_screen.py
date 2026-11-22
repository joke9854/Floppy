"""The web History screen (v2 P4-E).

`GET /api/v1/history/screen/` reads the Django History page's own context
(`build_history_context`): the month view from the history cache, or the
paginated view for filters, date ranges, release dates and "on this day".
Each row is written as the page's `ct/history_row.html` writes it.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import serializers

from app.models import MediaTypes
from app.templatetags import app_tags
from users.templatetags import user_tags

from .track_screen import TRACK_SCREEN_TYPES

# The page's type pills (ct/history_header.html).
_PILL_TYPES = {"tv", "movie", "anime", "game", "music", "book", "manga", "comic", "podcast", "boardgame"}
_SQUARE = {MediaTypes.MUSIC.value, MediaTypes.PODCAST.value}
_RANGES = {MediaTypes.GAME.value, MediaTypes.BOARDGAME.value}


def _get(value, key, default=None):
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _time(entry, user, mode) -> str:
    media_type = entry.get("media_type")
    if mode == "release":
        return str(_("Released"))
    if media_type == MediaTypes.MUSIC.value and entry.get("time_range_display"):
        return str(entry["time_range_display"])
    if entry.get("progress_display") and media_type in _RANGES:
        return str(entry.get("date_range_display") or "")
    played = entry.get("played_at_local")
    return str(user_tags.user_time_format(played, user)) if played else ""


def _href(entry) -> str:
    media_type = entry.get("media_type")
    album = entry.get("album")
    show = entry.get("show") or {}
    if media_type == MediaTypes.MUSIC.value and album:
        return str(app_tags.music_album_url(album) or "")
    if media_type == MediaTypes.PODCAST.value and _get(show, "podcast_uuid"):
        title = _get(show, "slug") or app_tags.slug(_get(show, "title") or "") or "show"
        return reverse(
            "media_details",
            kwargs={
                "source": "pocketcasts",
                "media_type": "podcast",
                "media_id": _get(show, "podcast_uuid"),
                "title": title,
            },
        )
    return str(app_tags.media_url(entry.get("item")) or "") if entry.get("item") else ""


def _poster(entry) -> str:
    poster = entry.get("poster")
    if entry.get("media_type") == MediaTypes.MOVIE.value and entry.get("item"):
        poster = app_tags.ct_poster(entry["item"]) or poster
    return str(app_tags.image_url(app_tags.tmdb_size(poster, "w154")) or "")


def _subtitle(entry, title) -> tuple[str, str]:
    """Return (code, text) as the row's second line."""
    media_type = entry.get("media_type")
    if entry.get("episode_code"):
        return str(entry["episode_code"]), title
    if media_type == MediaTypes.MUSIC.value:
        count = entry.get("play_count") or 1
        return ngettext("%(value_1)s play", "%(value_1)s plays", count) % {"value_1": count}, ""
    if media_type == MediaTypes.PODCAST.value:
        show = _get(entry.get("show") or {}, "title") or ""
        text = f"{show} · " if show else ""
        return "", text + str(app_tags.media_type_readable(media_type))
    if media_type == MediaTypes.MOVIE.value:
        return "", str(app_tags.media_type_readable(media_type))
    if entry.get("progress_display"):
        return str(entry["progress_display"]), ""
    try:
        return "", str(app_tags.media_type_readable(media_type))
    except ValueError:
        return "", str(media_type or "")


def _history_link(entry) -> str:
    """Return the row's View your activity history query (/history for the title)."""
    media_type = entry.get("media_type")
    item = entry.get("item") or {}
    album = entry.get("album")
    show = entry.get("show")
    if media_type == MediaTypes.MUSIC.value and album:
        query = {"album": _get(album, "id")}
    elif media_type == MediaTypes.PODCAST.value and show:
        query = {"media_type": MediaTypes.PODCAST.value, "podcast_show": _get(show, "id")}
    elif media_type == MediaTypes.EPISODE.value:
        query = {"media_type": MediaTypes.TV.value, "media_id": _get(item, "media_id"), "source": _get(item, "source")}
        if _get(item, "season_number"):
            query["season_number"] = _get(item, "season_number")
    else:
        query = {"media_type": media_type, "media_id": _get(item, "media_id"), "source": _get(item, "source")}
    if media_type in _RANGES:
        query["logging_style"] = "sessions"
    return urlencode(query)


def _track(entry) -> dict | None:
    """Return what the row's Edit tracking opens in the web dialog, or None."""
    item = entry.get("item")
    if not item:
        return None
    kwargs = app_tags.media_view_kwargs("track_modal", item)
    if kwargs is None or kwargs["media_type"] not in TRACK_SCREEN_TYPES:
        return None
    instance_id = entry.get("instance_id")
    if kwargs["media_type"] != _get(item, "media_type"):
        instance_id = None
    return {
        "media_type": kwargs["media_type"],
        "source": str(kwargs["source"]),
        "media_id": str(kwargs["media_id"]),
        "season_number": _get(item, "season_number"),
        "episode_number": _get(item, "episode_number")
        if kwargs["media_type"] == MediaTypes.EPISODE.value
        else None,
        "instance_id": instance_id,
    }


def history_entry(entry, user, mode) -> dict:
    """Return one history row for the web."""
    item = entry.get("item") or {}
    title = str(app_tags.display_title(item, user) or entry.get("display_title") or entry.get("title") or "")
    show_title = _get(entry.get("show") or {}, "title")
    code, text = _subtitle(entry, title)
    score = entry.get("score")
    played = entry.get("played_at_local")
    actions = mode != "release" and bool(_get(item, "media_type"))
    return {
        "key": str(entry.get("entry_key") or ""),
        "media_type": str(entry.get("media_type") or ""),
        "item_id": _get(item, "id"),
        "time": _time(entry, user, mode),
        "time_title": str(user_tags.user_datetime_format(played, user)) if played else "",
        "href": _href(entry),
        "poster": _poster(entry),
        "square": entry.get("media_type") in _SQUARE,
        "title": str(show_title) if entry.get("media_type") == MediaTypes.EPISODE.value and show_title else title,
        "code": code,
        "subtitle": text,
        "runtime": str(entry.get("runtime_display") or ""),
        "score": str(app_tags.score_display(score, user))
        if app_tags.show_media_score(score, user)
        else None,
        "track": _track(entry) if actions else None,
        "history_query": _history_link(entry) if actions else None,
    }


def history_day(day, user, mode) -> dict:
    """Return one day group for the web."""
    entries = day.get("entries") or []
    if mode == "release":
        count = day["release_count"] if day.get("release_count") is not None else len(entries)
        meta = ngettext("%(value_1)s release", "%(value_1)s releases", count) % {"value_1": count}
    else:
        count = day.get("entry_count", len(entries))
        meta = ngettext("%(value_1)s item · %(value_3)s", "%(value_1)s items · %(value_3)s", count) % {
            "value_1": count,
            "value_3": day.get("total_runtime_display") or "",
        }
    has_more = bool(day.get("has_more"))
    return {
        "key": str(day.get("day_key") or ""),
        "weekday": str(day.get("weekday") or ""),
        "date": str(day.get("date_display") or day.get("date") or ""),
        "meta": str(meta),
        "entries": [history_entry(entry, user, mode) for entry in entries],
        "more_url": (
            reverse("history_day_fragment", kwargs={"day_key": day["day_key"]}) + "?" + (day.get("next_entry_query") or "")
        )
        if has_more and day.get("day_key")
        else "",
        "remaining": int(day.get("remaining_entry_count") or 0) if has_more else 0,
    }


def _lists(user) -> list[dict]:
    from lists.models import CustomList

    return [
        {"value": str(list_id), "label": str(name)}
        for list_id, name in CustomList.objects.get_user_lists(user)
        .filter(is_smart=False)
        .prefetch_related(None)
        .order_by("name")
        .values_list("id", "name")
    ]


def build_history_screen(request) -> dict:
    """Return the History screen for the web from the page's context."""
    from app.history_views import build_history_context

    context = build_history_context(request)
    user = request.user
    mode = context.get("history_mode") or "activity"
    month = None
    if context.get("use_month_view"):
        nav = context.get("month_nav_query") or ""

        def link(year, month_number):
            query = f"year={year}&m={month_number}"
            return f"{query}&{nav}" if nav else query

        month = {
            "year": context["view_year"],
            "month": context["view_month"],
            "name": str(context.get("month_name") or ""),
            "current": None
            if context.get("is_current_month")
            else {"label": str(context["current_year"]), "query": link(context["current_year"], context["current_month_num"])},
            "newer": {
                "label": str(context["next_month_name"]),
                "query": link(context["next_year"], context["next_month"]),
            }
            if context.get("show_next_month")
            else None,
            "older": {
                "label": str(context["prev_month_name"]),
                "query": link(context["prev_year"], context["prev_month"]),
            },
            "year_back": {
                "label": str(context["view_year"] - 1),
                "query": link(context["view_year"] - 1, context["view_month"]),
            },
        }
    library = app_tags.ct_library_types(user)
    return {
        "mode": mode,
        "refreshing": bool(context.get("history_refreshing")),
        "media_type": str(request.GET.get("media_type") or ""),
        "filters": {str(key): str(value) for key, value in (context.get("active_filters") or {}).items()},
        "types": [
            {"value": entry["media_type"], "label": str(entry["display_name"])}
            for entry in library["types"]
            if entry["media_type"] in _PILL_TYPES
        ],
        "month": month,
        "page": int(context.get("current_page") or 1),
        "pages": int(context.get("total_pages") or 1),
        "days": [history_day(day, user, mode) for day in context.get("history_days") or []],
        "lists": _lists(user),
    }


class HistoryScreenChoiceSerializer(serializers.Serializer):
    """A value and its label."""

    value = serializers.CharField()
    label = serializers.CharField()


class HistoryScreenMonthLinkSerializer(serializers.Serializer):
    """A month navigation link."""

    label = serializers.CharField()
    query = serializers.CharField(help_text="The History page query for that month.")


class HistoryScreenMonthSerializer(serializers.Serializer):
    """The month view's navigation (history.html)."""

    year = serializers.IntegerField()
    month = serializers.IntegerField()
    name = serializers.CharField()
    current = HistoryScreenMonthLinkSerializer(allow_null=True, help_text="Back to this month; null when on it.")
    newer = HistoryScreenMonthLinkSerializer(allow_null=True)
    older = HistoryScreenMonthLinkSerializer()
    year_back = HistoryScreenMonthLinkSerializer()


class HistoryScreenTrackTargetSerializer(serializers.Serializer):
    """The track dialog target (GET /api/v1/track/...)."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    media_id = serializers.CharField()
    season_number = serializers.IntegerField(allow_null=True)
    episode_number = serializers.IntegerField(allow_null=True)
    instance_id = serializers.IntegerField(allow_null=True)


class HistoryScreenEntrySerializer(serializers.Serializer):
    """One play, as ct/history_row.html writes it."""

    key = serializers.CharField()
    media_type = serializers.CharField()
    item_id = serializers.IntegerField(allow_null=True, help_text="For Add to List.")
    time = serializers.CharField()
    time_title = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True, help_text="The title's Django page.")
    poster = serializers.CharField(allow_blank=True)
    square = serializers.BooleanField()
    title = serializers.CharField(allow_blank=True)
    code = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    runtime = serializers.CharField(allow_blank=True)
    score = serializers.CharField(allow_null=True)
    track = HistoryScreenTrackTargetSerializer(allow_null=True, help_text="Edit tracking in the web dialog.")
    history_query = serializers.CharField(allow_null=True, help_text="The History query for this title.")


class HistoryScreenDaySerializer(serializers.Serializer):
    """One day group, as ct/history_day.html writes it."""

    key = serializers.CharField()
    weekday = serializers.CharField()
    date = serializers.CharField()
    meta = serializers.CharField()
    entries = HistoryScreenEntrySerializer(many=True)
    more_url = serializers.CharField(
        allow_blank=True, help_text="GET with `Accept: application/json` for the day's next entries."
    )
    remaining = serializers.IntegerField()


class HistoryScreenSerializer(serializers.Serializer):
    """The History page: the month view, or a page of a filtered view."""

    mode = serializers.ChoiceField(choices=["activity", "release"])
    refreshing = serializers.BooleanField()
    media_type = serializers.CharField(allow_blank=True)
    filters = serializers.DictField(child=serializers.CharField(), help_text="The active filters.")
    types = HistoryScreenChoiceSerializer(many=True)
    month = HistoryScreenMonthSerializer(allow_null=True, help_text="Null outside the month view.")
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    days = HistoryScreenDaySerializer(many=True)
    lists = HistoryScreenChoiceSerializer(many=True)
