"""The web Library's data (v2 P4-B): the Django Library page, as JSON.

`app.media_list_views.build_media_list_context` is the page's own builder,
so this lists exactly what /medialist/<type> lists: the same filters, sorts,
saved preferences and pages. Like the page it saves the sort, direction and
status preferences, which is why the route takes the session or the account
token only. Cards use the template helpers the grid uses.

B1 covers the types drawn with the standard poster card; music, podcasts and
comics have their own grids on the page and come later.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from rest_framework import serializers

from app.models import MediaTypes, Status
from app.templatetags import app_tags

LIBRARY_SCREEN_TYPES = (
    MediaTypes.TV.value,
    MediaTypes.SEASON.value,
    MediaTypes.MOVIE.value,
    MediaTypes.ANIME.value,
    MediaTypes.MANGA.value,
    MediaTypes.GAME.value,
    MediaTypes.BOOK.value,
    MediaTypes.BOARDGAME.value,
)

_SPACES = re.compile(r"\s+")


def card_progress(item, media, user) -> dict | None:
    """Return the inset progress line of a poster card (media_card.html's rule).

    In progress or paused, counted media only, and only with the user's
    progress bar preference on.
    """
    if media is None or not user.progress_bar:
        return None
    status = getattr(media, "aggregated_status", None) or getattr(media, "status", None)
    if status not in (Status.IN_PROGRESS.value, Status.PAUSED.value):
        return None
    max_progress = getattr(media, "max_progress", None)
    count = getattr(media, "progress", None)
    if item.media_type == MediaTypes.MOVIE.value or not max_progress or not count:
        return None
    percent = app_tags.safe_attr(media, "progress_percentage")
    if percent is None:
        percent = min(100, round(count * 100 / max_progress))
    return {"percent": int(percent), "paused": status == Status.PAUSED.value}


def _sort_detail(request, entry, current_sort) -> str:
    """Return the card's line for the current sort, from the grid's own template."""
    html = render_to_string(
        "app/components/ct/library_sort_detail.html",
        {"media": entry, "current_sort": current_sort, "user": request.user},
        request=request,
    )
    return _SPACES.sub(" ", strip_tags(html)).strip()


def _card(request, entry, current_sort) -> dict:
    item = entry.item
    media = getattr(entry, "media", None)
    if item.media_type == MediaTypes.SEASON.value:
        title = app_tags.season_card_title(item)
    else:
        title = app_tags.display_title(item, request.user)
    image = (
        getattr(media, "card_image_override", None) or app_tags.ct_poster(item) or settings.IMG_NONE
    )
    status = getattr(entry, "aggregated_status", None) or getattr(entry, "status", None)
    return {
        "key": item.id,
        "media_type": item.media_type,
        "title": title,
        "url": app_tags.media_url(item),
        "poster": app_tags.image_url(app_tags.tmdb_size(image, "w342")),
        "poster_srcset": app_tags.tmdb_srcset(image, "w185,w342"),
        "status": status or None,
        "progress": card_progress(item, entry, request.user),
        "subtitle": str(app_tags.ct_library_subtitle(entry) or ""),
        "detail": _sort_detail(request, entry, current_sort) if current_sort else "",
    }


def _sort_choices(context) -> list[dict]:
    """Return the sorts the page's menu offers (critic rating, author gated as there)."""
    choices = []
    for value, label in context["sort_choices"]:
        if value == "critic_rating" and not context.get("supports_critic_rating_sort"):
            continue
        if value == "author" and not (context.get("filter_data") or {}).get("show_authors"):
            continue
        choices.append({"value": value, "label": str(label)})
    return choices


def build_library_screen(request, media_type) -> dict:
    """Return the Library page for ``media_type`` as the web screen reads it."""
    from app.media_list_views import build_media_list_context

    context, _layout, _resolved = build_media_list_context(request, media_type)
    page = context["media_list"]
    user = request.user
    library = app_tags.ct_library_types(user)
    views = []
    if library["tv_seasons"] and media_type in (MediaTypes.TV.value, MediaTypes.SEASON.value):
        views = [
            {"media_type": MediaTypes.TV.value, "label": "Shows"},
            {"media_type": MediaTypes.SEASON.value, "label": "Seasons"},
        ]
    current_sort = context["current_sort"]
    app_tags.ct_prefetch_posters(list(page), "item")
    return {
        "media_type": media_type,
        "title": str(app_tags.media_type_readable_plural(media_type)),
        "count": page.paginator.count if getattr(page, "paginator", None) else len(page),
        "in_progress": app_tags.ct_library_in_progress(user, media_type) or 0,
        "views": views,
        "sort": current_sort,
        "direction": context["current_direction"],
        "sorts": _sort_choices(context),
        "statuses": [str(value) for value in context["current_status"]],
        "status_choices": [
            {"value": str(value), "label": str(label)}
            for value, label in context["status_choices"]
            if value not in ("all", "All")
        ],
        "search": request.GET.get("search", ""),
        "page": page.number if hasattr(page, "number") else 1,
        "has_next": bool(getattr(page, "has_next", lambda: False)()),
        "results": [_card(request, entry, current_sort) for entry in page],
    }


class LibraryCardProgressSerializer(serializers.Serializer):
    """The inset progress line."""

    percent = serializers.IntegerField()
    paused = serializers.BooleanField()


class LibraryCardSerializer(serializers.Serializer):
    """A Library poster card."""

    key = serializers.IntegerField(help_text="The item id.")
    media_type = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField(help_text="The Django page the card opens.")
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    status = serializers.CharField(allow_null=True)
    progress = LibraryCardProgressSerializer(allow_null=True)
    subtitle = serializers.CharField(
        allow_blank=True, help_text='"S2 E5 next" for shows in progress, else the status.'
    )
    detail = serializers.CharField(
        allow_blank=True, help_text="The value the list is sorted by, as the page shows it."
    )


class LibraryChoiceSerializer(serializers.Serializer):
    """A sort or status the page offers."""

    value = serializers.CharField()
    label = serializers.CharField()


class LibraryViewSerializer(serializers.Serializer):
    """Shows or Seasons, when both TV views are on."""

    media_type = serializers.CharField()
    label = serializers.CharField()


class LibraryScreenSerializer(serializers.Serializer):
    """One page of the Library for a media type, with its menus' state."""

    media_type = serializers.CharField()
    title = serializers.CharField()
    count = serializers.IntegerField(help_text="Titles matching the filters, all pages.")
    in_progress = serializers.IntegerField()
    views = LibraryViewSerializer(many=True)
    sort = serializers.CharField()
    direction = serializers.CharField(help_text='"asc" or "desc".')
    sorts = LibraryChoiceSerializer(many=True)
    statuses = serializers.ListField(
        child=serializers.CharField(), help_text="Selected statuses; empty for all."
    )
    status_choices = LibraryChoiceSerializer(many=True)
    search = serializers.CharField(allow_blank=True)
    page = serializers.IntegerField()
    has_next = serializers.BooleanField()
    results = LibraryCardSerializer(many=True)
