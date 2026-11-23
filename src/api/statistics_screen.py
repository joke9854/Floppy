"""The web Statistics screen (v2 P4-H).

`GET /api/v1/statistics/screen/` reads the Django Statistics page's own
context (`build_statistics_context`) for the page's `start-date`, `end-date`
and `compare`. H1: the range, media-type and compare controls, the hero, the
highlight cards, the summary cards, Activity History (heatmap) or Played
Hours by Media Type (stacked, by day), and the Statistics Preferences. The
media-type switch is the browser's, as on the page: every type's summary and
highlights come at once. `/api/v1/statistics/overview/` stays the CineTrack
app's contract.
"""

from __future__ import annotations

import math
from datetime import date, datetime

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers

from app import statistics_cache
from app.templatetags import app_tags
from users.templatetags import user_tags

# The page's media-type dropdown (statistics.html initialMediaTypeOptions).
_MEDIA_TYPES = (
    ("all", "All media", None),
    ("tv", "TV Shows", None),
    ("movie", "Movies", None),
    ("anime", "Anime", None),
    ("manga", "Manga", "manga_enabled"),
    ("game", "Games", None),
    ("boardgame", "Board Games", "boardgame_enabled"),
    ("music", "Music", "music_enabled"),
    ("podcast", "Podcasts", "podcast_enabled"),
    ("book", "Books", "book_enabled"),
    ("comic", "Comics", "comic_enabled"),
)
_COMPARE_OPTIONS = (
    ("previous_period", "Previous period"),
    ("last_year", "Last year"),
    ("none", "No comparison"),
)


def _date_label(user, value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return value
    return str(user_tags.user_date_format(value, user) or "")


def _range_label(user, start, end) -> str:
    from app.statistics_views import _format_statistics_range_label

    return str(_format_statistics_range_label(user, start, end))


def _aware(day: date | None, *, end: bool = False):
    if day is None:
        return None
    moment = datetime.combine(day, datetime.max.time() if end else datetime.min.time())
    return timezone.make_aware(moment, timezone.get_current_timezone())


def _ranges(user) -> list[dict]:
    """Return the predefined ranges with their dates, as the range dropdown lists them."""
    from app.statistics_views import _get_predefined_range_date_strings

    today = timezone.localdate()
    ranges = []
    for name in statistics_cache.PREDEFINED_RANGES:
        start, end = _get_predefined_range_date_strings(name, today, "%Y-%m-%d")
        if start == "all":
            dates = _("All activity")
        else:
            dates = _range_label(
                user,
                _aware(date.fromisoformat(start)),
                _aware(date.fromisoformat(end), end=True),
            )
        ranges.append({"name": name, "start": start or "", "end": end or "", "dates": dates})
    return ranges


def _compare_options(user, start, end) -> list[dict]:
    from app.statistics_views import _resolve_statistics_comparison_range

    options = []
    for value, label in _COMPARE_OPTIONS:
        dates = ""
        if value != "none" and start and end:
            compare_start, compare_end = _resolve_statistics_comparison_range(start, end, value)
            dates = _range_label(user, compare_start, compare_end) if compare_start else ""
        options.append({"value": value, "label": _(label), "dates": dates})
    return options


def _summary(user, stats: dict) -> dict:
    total_minutes = float(stats.get("total_minutes") or 0)
    start = stats.get("longest_streak_start")
    end = stats.get("longest_streak_end")
    streak_dates = ""
    if start:
        streak_dates = (
            _date_label(user, start)
            if str(start) == str(end)
            else f"{_date_label(user, start)} \u2013 {_date_label(user, end)}"
        )
    average = stats.get("average_score")
    return {
        "total": int(stats.get("total") or 0),
        "completed": int(stats.get("completed") or 0),
        "total_hours": round(total_minutes / 60),
        "total_days": math.floor(total_minutes / 60 / 24),
        "has_score": bool(stats.get("has_score")),
        "average_score": "" if average is None else f"{float(average):.2f}".rstrip("0").rstrip("."),
        "most_active_day": str(stats.get("most_active_day") or ""),
        "most_active_day_percentage": int(stats.get("most_active_day_percentage") or 0),
        "current_streak": int(stats.get("current_streak") or 0),
        "longest_streak": int(stats.get("longest_streak") or 0),
        "longest_streak_dates": streak_dates,
    }


def _play(user, play) -> dict | None:
    if not play:
        return None
    image = play.get("image")
    return {
        "title": str(play.get("title") or ""),
        "image": str(app_tags.image_url(image) or "") if image else "",
        "href": str(app_tags.media_url(play.get("item")) or "") if play.get("item") else "",
        "caption": _("Played %(date)s") % {"date": _date_label(user, play.get("played_at"))},
    }


def _highlights(user, highlights: dict | None) -> dict:
    highlights = highlights or {}
    card = highlights.get("today_card") or {}
    today = None
    entry = card.get("entry")
    if entry:
        query = f"month={highlights.get('today_month')}&day={highlights.get('today_day')}"
        if card.get("use_release_url"):
            query = f"history_mode=release&{query}"
        image = entry.get("image")
        today = {
            "title": str(entry.get("title") or ""),
            "image": str(app_tags.image_url(image) or "") if image else "",
            "href": f"{reverse('history')}?{query}",
            "caption": f"{card.get('date_prefix') or ''} {card.get('year') or ''}".strip(),
        }
    return {
        "first_play": _play(user, highlights.get("first_play")),
        "last_play": _play(user, highlights.get("last_play")),
        "today_label": str(card.get("label") or _("TODAY IN HISTORY")),
        "today": today,
    }


def _activity(comparison: dict | None, period_label: str) -> dict:
    comparison = comparison or {}
    tooltip = comparison.get("tooltip") or None
    return {
        "badge": str(comparison.get("badge") or ""),
        "state": str(comparison.get("badge_state") or "none"),
        "details": str(comparison.get("details") or ""),
        "period_label": str(period_label or ""),
        "tooltip": (
            {
                "current_label": str(tooltip.get("current_label") or ""),
                "current_total": str(tooltip.get("current_total") or ""),
                "comparison_label": str(tooltip.get("comparison_label") or ""),
                "comparison_total": str(tooltip.get("comparison_total") or ""),
            }
            if tooltip
            else None
        ),
    }


def _heatmap(activity_data) -> dict | None:
    if not activity_data or not activity_data.get("calendar_weeks"):
        return None
    return {
        "months": [{"label": str(label), "weeks": int(weeks)} for label, weeks in activity_data.get("months") or []],
        "weekdays": [_(str(label)) for label in activity_data.get("weekday_labels") or []],
        "weeks": [
            [
                {
                    "date": str(day.get("date") or ""),
                    "count": int(day.get("count") or 0),
                    "level": int(day.get("level") or 0),
                    "future": bool(day.get("future")),
                }
                for day in week
            ]
            for week in activity_data["calendar_weeks"]
        ],
    }


def _played_hours(daily) -> dict:
    daily = daily or {}
    return {
        "days": [str(label) for label in daily.get("labels") or []],
        "series": [
            {
                "label": _(str(dataset.get("label") or "")),
                "media_type": str(dataset.get("media_type") or ""),
                "color": str(dataset.get("background_color") or dataset.get("backgroundColor") or ""),
                "values": [float(value or 0) for value in dataset.get("data") or []],
            }
            for dataset in daily.get("datasets") or []
        ],
    }


_GENRE_TYPES = ("tv", "movie", "anime", "music", "game")


def _series(chart) -> dict:
    """Return a Chart.js-shaped {labels, datasets} as {labels, series}."""
    chart = chart or {}
    return {
        "labels": [str(label) for label in chart.get("labels") or []],
        "series": [
            {
                "label": str(dataset.get("label") or ""),
                "media_type": str(dataset.get("media_type") or ""),
                "color": str(dataset.get("background_color") or dataset.get("backgroundColor") or ""),
                "values": [float(value or 0) for value in dataset.get("data") or []],
            }
            for dataset in chart.get("datasets") or []
        ],
    }


def _number_list(values) -> list[float]:
    return [float(value or 0) for value in values or []]


def _consumption_metric(metric) -> dict | None:
    if not metric:
        return None
    return {
        "label": str(metric.get("label") or ""),
        "unit": str(metric.get("unit") or ""),
        "per_year": float(metric.get("per_year") or 0),
        "per_month": float(metric.get("per_month") or 0),
        "per_day": float(metric.get("per_day") or 0),
    }


def _charts(context) -> dict:
    """Return the H2 charts that follow the media-type switch (statistics-charts.js)."""
    distribution = context.get("media_type_distribution") or {}
    dataset = (distribution.get("datasets") or [{}])[0]
    colors = dataset.get("backgroundColor") or dataset.get("background_color") or []
    combined = context.get("combined_plays_charts") or {}
    status = context.get("status_distribution") or {}
    scores = context.get("score_distribution") or {}
    return {
        "rhythm": {
            key: [[float(value or 0) for value in row] for row in matrix or []]
            for key, matrix in (context.get("weekday_hour_chart_data") or {}).items()
        },
        "hours_by_type": {
            "labels": [_(str(label)) for label in distribution.get("labels") or []],
            "values": _number_list(dataset.get("data")),
            "colors": [str(color) for color in colors] if isinstance(colors, list) else [],
        },
        "top_genres": {
            media_type: [
                {"name": str(genre.get("name") or ""), "hours": round(float(genre.get("minutes") or 0) / 60, 2)}
                for genre in (context.get(f"{media_type}_consumption") or {}).get("top_genres") or []
            ]
            for media_type in _GENRE_TYPES
        },
        "combined": {
            chart: {key: _series(value) for key, value in (combined.get(chart) or {}).items()}
            for chart in ("by_month", "by_weekday", "by_time_of_day")
        },
        "consumption": {
            media_type: {
                "has_data": bool(stats.get("has_data")),
                "primary": _consumption_metric(stats.get("primary")),
                "secondary": _consumption_metric(stats.get("secondary")),
                "bonuses": [
                    {
                        "kind": str(bonus.get("kind") or ""),
                        "label": str(bonus.get("label") or ""),
                        "unit": str(bonus.get("unit") or ""),
                        "value": float(bonus.get("value") or 0),
                    }
                    for bonus in stats.get("bonuses") or []
                ],
            }
            for media_type, stats in (context.get("consumption_stats_by_type") or {}).items()
            if isinstance(stats, dict)
        },
        "status": _series(status),
        "ratings": _series(scores),
    }


def _preferences(user) -> dict:
    from app.providers import tvdb

    return {
        "activity_history_view": str(getattr(user, "activity_history_view", "heatmap") or "heatmap"),
        "duration_format": str(getattr(user, "duration_format", "hours_minutes") or "hours_minutes"),
        "week_start_day": str(getattr(user, "week_start_day", "monday") or "monday"),
        "rating_scale": str(getattr(user, "rating_scale", "10") or "10"),
        "stats_split_tv_anime": bool(getattr(user, "stats_split_tv_anime", False)),
        # The page offers the anime split only without the Anime type, with TVDB.
        "show_anime_split": not getattr(user, "anime_enabled", False) and bool(tvdb.enabled()),
    }


def build_statistics_screen(request) -> dict:
    """Return the Statistics screen (H1) for the web from the page's context."""
    from app.statistics_views import build_statistics_context

    context = build_statistics_context(request)
    user = request.user
    start, end = context.get("start_date"), context.get("end_date")
    if isinstance(start, date) and not isinstance(start, datetime):
        start, end = _aware(start), _aware(end, end=True)
    range_name = context.get("selected_range_name") or ""
    summaries = {
        media_type: _summary(user, stats or {})
        for media_type, stats in (context.get("summary_stats_by_type") or {}).items()
    }
    highlights = {"all": _highlights(user, context.get("history_highlights"))}
    for media_type, type_highlights in (context.get("history_highlights_by_type") or {}).items():
        highlights[media_type] = _highlights(user, type_highlights)
    return {
        "database_error": bool(context.get("database_error")),
        "range": {
            "name": str(range_name),
            "start": str(context.get("start_date_str") or ""),
            "end": str(context.get("end_date_str") or ""),
            "label": str(context.get("selected_range_dates_label") or ""),
            "finite": bool(start and end),
            "predefined": range_name in statistics_cache.PREDEFINED_RANGES,
            "first_day": start.date().isoformat() if isinstance(start, datetime) else "",
            "last_day": end.date().isoformat() if isinstance(end, datetime) else "",
        },
        "ranges": _ranges(user),
        "compare": {
            "mode": str(context.get("selected_compare_mode") or "none"),
            "options": _compare_options(user, start, end),
        },
        "media_types": [
            {"value": value, "label": _(label)}
            for value, label, flag in _MEDIA_TYPES
            if flag is None or getattr(user, flag, False)
        ],
        "summaries": summaries,
        "highlights": highlights,
        "activity": _activity(
            context.get("total_activity_comparison"),
            context.get("activity_comparison_period_label") or "",
        ),
        "rating_scale_max": int(app_tags.rating_scale_max(user)),
        "heatmap": _heatmap(context.get("activity_data")),
        "played_hours": _played_hours(context.get("daily_hours_by_media_type")),
        "preferences": _preferences(user),
        "charts": _charts(context),
        "urls": {
            "refresh": reverse("refresh_statistics"),
            "compare": reverse("update_statistics_compare_mode"),
            "preferences": reverse("update_statistics_preferences"),
            "recap": reverse("statistics_recap"),
            "status": reverse("cache_status"),
        },
    }


class StatisticsScreenRangeSerializer(serializers.Serializer):
    """The range shown: `start`/`end` are the page's query values (or `all`)."""

    name = serializers.CharField(allow_blank=True)
    start = serializers.CharField(allow_blank=True)
    end = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True)
    finite = serializers.BooleanField()
    predefined = serializers.BooleanField()
    first_day = serializers.CharField(allow_blank=True)
    last_day = serializers.CharField(allow_blank=True)


class StatisticsScreenPresetSerializer(serializers.Serializer):
    """A predefined range with its dates."""

    name = serializers.CharField()
    start = serializers.CharField()
    end = serializers.CharField()
    dates = serializers.CharField(allow_blank=True)


class StatisticsScreenChoiceSerializer(serializers.Serializer):
    """A compare option (with the compared dates) or a media type."""

    value = serializers.CharField()
    label = serializers.CharField()
    dates = serializers.CharField(allow_blank=True, required=False)


class StatisticsScreenCompareSerializer(serializers.Serializer):
    """Compare to: the saved mode and its options."""

    mode = serializers.CharField()
    options = StatisticsScreenChoiceSerializer(many=True)


class StatisticsScreenSummarySerializer(serializers.Serializer):
    """One type's summary (the hero and the summary cards)."""

    total = serializers.IntegerField()
    completed = serializers.IntegerField()
    total_hours = serializers.IntegerField()
    total_days = serializers.IntegerField()
    has_score = serializers.BooleanField()
    average_score = serializers.CharField(allow_blank=True)
    most_active_day = serializers.CharField(allow_blank=True)
    most_active_day_percentage = serializers.IntegerField()
    current_streak = serializers.IntegerField()
    longest_streak = serializers.IntegerField()
    longest_streak_dates = serializers.CharField(allow_blank=True)


class StatisticsScreenPlaySerializer(serializers.Serializer):
    """A highlight card: title, 3:2 image, its page, "Played …"."""

    title = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    caption = serializers.CharField(allow_blank=True)


class StatisticsScreenHighlightsSerializer(serializers.Serializer):
    """First Play, Last Play and the Today card for one type."""

    first_play = StatisticsScreenPlaySerializer(allow_null=True)
    last_play = StatisticsScreenPlaySerializer(allow_null=True)
    today_label = serializers.CharField()
    today = StatisticsScreenPlaySerializer(allow_null=True)


class StatisticsScreenTooltipSerializer(serializers.Serializer):
    """The Activity card's comparison tooltip."""

    current_label = serializers.CharField(allow_blank=True)
    current_total = serializers.CharField(allow_blank=True)
    comparison_label = serializers.CharField(allow_blank=True)
    comparison_total = serializers.CharField(allow_blank=True)


class StatisticsScreenActivitySerializer(serializers.Serializer):
    """The Activity card (all types): the badge and "vs {period}"."""

    badge = serializers.CharField(allow_blank=True)
    state = serializers.CharField()
    details = serializers.CharField(allow_blank=True)
    period_label = serializers.CharField(allow_blank=True)
    tooltip = StatisticsScreenTooltipSerializer(allow_null=True)


class StatisticsScreenMonthSerializer(serializers.Serializer):
    """A heatmap month label spanning `weeks` columns."""

    label = serializers.CharField()
    weeks = serializers.IntegerField()


class StatisticsScreenDaySerializer(serializers.Serializer):
    """A heatmap cell (level 0-4)."""

    date = serializers.CharField()
    count = serializers.IntegerField()
    level = serializers.IntegerField()
    future = serializers.BooleanField()


class StatisticsScreenHeatmapSerializer(serializers.Serializer):
    """Activity History: one column per week."""

    months = StatisticsScreenMonthSerializer(many=True)
    weekdays = serializers.ListField(child=serializers.CharField())
    weeks = serializers.ListField(child=StatisticsScreenDaySerializer(many=True))


class StatisticsScreenSeriesSerializer(serializers.Serializer):
    """A media type's hours per day."""

    label = serializers.CharField()
    media_type = serializers.CharField()
    color = serializers.CharField(allow_blank=True)
    values = serializers.ListField(child=serializers.FloatField())


class StatisticsScreenPlayedHoursSerializer(serializers.Serializer):
    """Played Hours by Media Type: days with activity, hours per type."""

    days = serializers.ListField(child=serializers.CharField())
    series = StatisticsScreenSeriesSerializer(many=True)


class StatisticsScreenBarSeriesSerializer(serializers.Serializer):
    """A chart series (a type, or a status)."""

    label = serializers.CharField(allow_blank=True)
    media_type = serializers.CharField(allow_blank=True)
    color = serializers.CharField(allow_blank=True)
    values = serializers.ListField(child=serializers.FloatField())


class StatisticsScreenChartSerializer(serializers.Serializer):
    """Labels and series, as the page's Chart.js payloads."""

    labels = serializers.ListField(child=serializers.CharField())
    series = StatisticsScreenBarSeriesSerializer(many=True)


class StatisticsScreenHoursByTypeSerializer(serializers.Serializer):
    """Hours by Media Type: one slice per type."""

    labels = serializers.ListField(child=serializers.CharField())
    values = serializers.ListField(child=serializers.FloatField())
    colors = serializers.ListField(child=serializers.CharField())


class StatisticsScreenGenreSerializer(serializers.Serializer):
    """A Top Genres slice."""

    name = serializers.CharField()
    hours = serializers.FloatField()


class StatisticsScreenMetricSerializer(serializers.Serializer):
    """A consumption metric per year, month and day."""

    label = serializers.CharField(allow_blank=True)
    unit = serializers.CharField(allow_blank=True)
    per_year = serializers.FloatField()
    per_month = serializers.FloatField()
    per_day = serializers.FloatField()


class StatisticsScreenBonusSerializer(serializers.Serializer):
    """A consumption bonus tile (playtime, length, ...)."""

    kind = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True)
    unit = serializers.CharField(allow_blank=True)
    value = serializers.FloatField()


class StatisticsScreenConsumptionSerializer(serializers.Serializer):
    """A type's consumption tiles."""

    has_data = serializers.BooleanField()
    primary = StatisticsScreenMetricSerializer(allow_null=True)
    secondary = StatisticsScreenMetricSerializer(allow_null=True)
    bonuses = StatisticsScreenBonusSerializer(many=True)


class StatisticsScreenCombinedSerializer(serializers.Serializer):
    """Hours by Month, Day of Week and Time of Day, per type key."""

    by_month = serializers.DictField(child=StatisticsScreenChartSerializer())
    by_weekday = serializers.DictField(child=StatisticsScreenChartSerializer())
    by_time_of_day = serializers.DictField(child=StatisticsScreenChartSerializer())


class StatisticsScreenChartsSerializer(serializers.Serializer):
    """H2: the charts that follow the media-type switch."""

    rhythm = serializers.DictField(
        child=serializers.ListField(child=serializers.ListField(child=serializers.FloatField())),
        help_text="Per type key: 7 weekday rows (Monday first) of 24 hours.",
    )
    hours_by_type = StatisticsScreenHoursByTypeSerializer()
    top_genres = serializers.DictField(child=StatisticsScreenGenreSerializer(many=True))
    combined = StatisticsScreenCombinedSerializer()
    consumption = serializers.DictField(child=StatisticsScreenConsumptionSerializer())
    status = StatisticsScreenChartSerializer(help_text="Labels are types; a series per status.")
    ratings = StatisticsScreenChartSerializer(help_text="Labels are scores; a series per type.")


class StatisticsScreenPreferencesSerializer(serializers.Serializer):
    """Statistics Preferences (posted to `urls.preferences`)."""

    activity_history_view = serializers.CharField()
    duration_format = serializers.CharField()
    week_start_day = serializers.CharField()
    rating_scale = serializers.CharField()
    stats_split_tv_anime = serializers.BooleanField()
    show_anime_split = serializers.BooleanField()


class StatisticsScreenUrlsSerializer(serializers.Serializer):
    """Where the page's controls post, and the recap page."""

    refresh = serializers.CharField()
    compare = serializers.CharField()
    preferences = serializers.CharField()
    recap = serializers.CharField()
    status = serializers.CharField()


class StatisticsScreenSerializer(serializers.Serializer):
    """The Statistics page for the web app (H1)."""

    database_error = serializers.BooleanField()
    range = StatisticsScreenRangeSerializer()
    ranges = StatisticsScreenPresetSerializer(many=True)
    compare = StatisticsScreenCompareSerializer()
    media_types = StatisticsScreenChoiceSerializer(many=True)
    summaries = serializers.DictField(child=StatisticsScreenSummarySerializer())
    highlights = serializers.DictField(child=StatisticsScreenHighlightsSerializer())
    activity = StatisticsScreenActivitySerializer()
    rating_scale_max = serializers.IntegerField()
    heatmap = StatisticsScreenHeatmapSerializer(allow_null=True)
    played_hours = StatisticsScreenPlayedHoursSerializer()
    preferences = StatisticsScreenPreferencesSerializer()
    charts = StatisticsScreenChartsSerializer()
    urls = StatisticsScreenUrlsSerializer()

