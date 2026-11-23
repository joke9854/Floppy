"""The Statistics screen's talent section (v2 P4-H3).

`GET /api/v1/statistics/talent/` reads the Django talent fragment's own
context (`build_talent_fragment_context`, the page's lazy
statistics_talent_fragment) for the page's range and compare. As the page
does after a change, `media_type` (tv, movie, anime, game) re-aggregates the
role leaders, the featured player and the studios for that type
(update_top_talent_sort), and `person_source` + `person_id` feature a picked
person (select_featured_person). The sorts post to the page's own views.
"""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import serializers

from app import stats_cast_crew
from app.templatetags import app_tags

TALENT_TYPES = ("tv", "movie", "anime", "game")


def _person_href(person) -> str:
    try:
        return reverse(
            "person_detail",
            kwargs={
                "source": person.get("source"),
                "person_id": person.get("person_id"),
                "name": slugify(person.get("name") or "") or "person",
            },
        )
    except NoReverseMatch:
        return ""


def _featured(person) -> dict | None:
    if not person:
        return None
    image = person.get("image")
    return {
        "name": str(person.get("name") or ""),
        "image": str(app_tags.image_url(image) or "") if image else "",
        "href": _person_href(person),
        "source": str(person.get("source") or ""),
        "person_id": str(person.get("person_id") or ""),
        "unique_titles": int(person.get("unique_titles") or 0),
        "unique_movies": int(person.get("unique_movies") or 0),
        "unique_shows": int(person.get("unique_shows") or 0),
        "unique_games": int(person.get("unique_games") or 0),
        "pct_of_library": float(person.get("pct_of_library") or 0),
        "known_for": [str(pill.get("label") or "") for pill in person.get("known_for_pills") or []],
    }


def _strip(row) -> dict:
    row = row or {}
    items = []
    for item in row.get("items") or []:
        image = item.get("image")
        items.append({
            "title": str(item.get("title") or ""),
            "href": str(app_tags.media_url(item) or ""),
            "image": str(app_tags.image_url(image) or "") if image else "",
            "caption": str(item.get("role") or item.get("year") or ""),
        })
    return {"title": str(row.get("title") or ""), "summary": str(row.get("summary") or ""), "items": items}


def _metric_plays(count) -> str:
    count = int(count or 0)
    return ngettext("%(value_1)s play", "%(value_1)s plays", count) % {"value_1": count}


def build_talent_screen(request) -> dict:
    """Return the talent section for the web, as the page shows it."""
    from app.statistics_talent import _aggregate_top_talent
    from app.statistics_views import (
        _resolve_statistics_range_inputs,
        build_talent_fragment_context,
    )

    context = build_talent_fragment_context(request)
    user = request.user
    sort = getattr(user, "top_talent_sort_by", "plays") or "plays"
    start, end = _resolve_statistics_range_inputs(
        request.GET.get("range_name") or None,
        request.GET.get("start-date") or None,
        request.GET.get("end-date") or None,
    )
    total = int((context.get("media_count") or {}).get("total", 0) or 0)
    role_leaders = context.get("role_leaders") or {}
    featured = context.get("featured_person")
    strip = context.get("person_media_strip") or []
    studios = context.get("studio_footprint") or {}

    media_type = request.GET.get("media_type") or ""
    if media_type in TALENT_TYPES:
        top_talent = _aggregate_top_talent(user, start, end, media_type=media_type)
        role_leaders = stats_cast_crew.get_role_leaders(top_talent, sort_by=sort)
        featured, strip = stats_cast_crew.get_featured_repeat_player_with_strip(
            user, start, end, top_talent, total_library_titles=total, sort_by=sort
        )
        studios = stats_cast_crew.get_studio_footprint(user, start, end, top_talent, media_type=media_type)

    source, person_id = request.GET.get("person_source"), request.GET.get("person_id")
    if source and person_id:
        picked, picked_strip = stats_cast_crew.get_featured_person_with_strip(
            user, source, person_id, start, end, total_library_titles=total, sort_by=sort
        )
        if picked:
            featured, strip = picked, picked_strip

    strip_row = stats_cast_crew.build_media_strip_row(
        strip,
        person_name=featured.get("name") if featured else None,
        total_titles=featured.get("unique_titles") if featured else None,
        sort_by=sort,
    )
    studio_sort = context.get("studio_sort_by") or "plays"
    genre_sort = context.get("genre_sort_by") or "time"
    return {
        "featured": _featured(featured),
        "strip": _strip(strip_row),
        "talent_sort": sort,
        "role_leaders": [
            {
                "bucket": str(column.get("bucket") or ""),
                "label": _(str(column.get("label") or "")),
                "people": [
                    {
                        "name": str(entry.get("name") or ""),
                        "source": str(entry.get("source") or ""),
                        "person_id": str(entry.get("person_id") or ""),
                        "metric": str(entry.get("display_metric") if entry.get("display_metric") is not None else ""),
                    }
                    for entry in column.get("entries") or []
                ],
            }
            for column in role_leaders.get("columns") or []
        ],
        "studio_sort": studio_sort,
        "studios": [
            {
                "name": str(studio.get("name") or ""),
                "pct": float(studio.get("pct") or 0),
                "metric": str(studio.get("watched_time") or "") if studio_sort == "time" else _metric_plays(studio.get("plays")),
            }
            for studio in studios.get("studios") or []
        ],
        "genre_sort": genre_sort,
        "genres": [
            {
                "name": str(genre.get("name") or ""),
                "pct": float(genre.get("pct") or 0),
                "color": str(genre.get("color") or ""),
                "metric": _metric_plays(genre.get("plays")) if genre_sort == "plays" else str(genre.get("formatted_duration") or ""),
            }
            for genre in context.get("top_genres_combined") or []
        ],
        "eras": [
            {
                "name": str(era.get("label") or ""),
                "pct": float(era.get("pct") or 0),
                "color": "",
                "metric": _metric_plays(era.get("plays")) if genre_sort == "plays" else str(era.get("formatted_duration") or ""),
            }
            for era in context.get("era_spotlight") or []
        ],
        "urls": {
            "talent_sort": reverse("update_top_talent_sort"),
            "studio_sort": reverse("update_studio_sort"),
            "genre_sort": reverse("update_genre_sort"),
        },
    }


class StatisticsTalentPersonSerializer(serializers.Serializer):
    """The Featured Repeat Player."""

    name = serializers.CharField()
    image = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    person_id = serializers.CharField()
    unique_titles = serializers.IntegerField()
    unique_movies = serializers.IntegerField()
    unique_shows = serializers.IntegerField()
    unique_games = serializers.IntegerField()
    pct_of_library = serializers.FloatField()
    known_for = serializers.ListField(child=serializers.CharField())


class StatisticsTalentStripItemSerializer(serializers.Serializer):
    """A title in the featured person's strip."""

    title = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_blank=True)
    caption = serializers.CharField(allow_blank=True)


class StatisticsTalentStripSerializer(serializers.Serializer):
    """The featured person's titles."""

    title = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    items = StatisticsTalentStripItemSerializer(many=True)


class StatisticsTalentLeaderSerializer(serializers.Serializer):
    """A role leader (`metric` per the talent sort)."""

    name = serializers.CharField()
    source = serializers.CharField(allow_blank=True)
    person_id = serializers.CharField(allow_blank=True)
    metric = serializers.CharField(allow_blank=True)


class StatisticsTalentColumnSerializer(serializers.Serializer):
    """A Role Leaders column (Actors, Actresses, Directors, Writers)."""

    bucket = serializers.CharField()
    label = serializers.CharField()
    people = StatisticsTalentLeaderSerializer(many=True)


class StatisticsTalentBarSerializer(serializers.Serializer):
    """A ranked bar: a studio, genre or decade."""

    name = serializers.CharField()
    pct = serializers.FloatField()
    color = serializers.CharField(allow_blank=True, required=False)
    metric = serializers.CharField(allow_blank=True)


class StatisticsTalentUrlsSerializer(serializers.Serializer):
    """Where the sorts post (`sort_by`)."""

    talent_sort = serializers.CharField()
    studio_sort = serializers.CharField()
    genre_sort = serializers.CharField()


class StatisticsTalentSerializer(serializers.Serializer):
    """The talent section: featured player, role leaders, studios, taste."""

    featured = StatisticsTalentPersonSerializer(allow_null=True)
    strip = StatisticsTalentStripSerializer()
    talent_sort = serializers.CharField()
    role_leaders = StatisticsTalentColumnSerializer(many=True)
    studio_sort = serializers.CharField()
    studios = StatisticsTalentBarSerializer(many=True)
    genre_sort = serializers.CharField()
    genres = StatisticsTalentBarSerializer(many=True)
    eras = StatisticsTalentBarSerializer(many=True)
    urls = StatisticsTalentUrlsSerializer()
