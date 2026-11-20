"""The web Library's data (v2 P4-B): the Django Library page, as JSON.

`app.media_list_views.build_media_list_context` is the page's own builder,
so this lists exactly what /medialist/<type> lists: the same filters, sorts,
saved preferences and pages. Like the page it saves the sort, direction and
status preferences, which is why the route takes the session or the account
token only. Cards use the template helpers the grid uses.

Music lists artists or albums (their own trackers, no Item) unless the
Tracks view is on; podcasts list shows through the page's adapter, which
carries an Item. Both draw square cards.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.utils.translation import gettext as _
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
    MediaTypes.MUSIC.value,
    MediaTypes.PODCAST.value,
    MediaTypes.COMIC.value,
)
_SQUARE_TYPES = (MediaTypes.MUSIC.value, MediaTypes.PODCAST.value)
_SUBVIEWS = {
    MediaTypes.MUSIC.value: (("artists", "Artists"), ("albums", "Albums"), ("tracks", "Tracks")),
    MediaTypes.COMIC.value: (("comics", "Comics"), ("issues", "Issues")),
}
_NEXT_EPISODE_TYPES = (MediaTypes.TV.value, MediaTypes.SEASON.value, MediaTypes.ANIME.value)

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


def _history_url(entry) -> str:
    """The card's history link, as media_card.html builds it."""
    from urllib.parse import urlencode

    from django.urls import reverse

    item = entry.item
    tracker = getattr(entry, "tracker", None)
    show = getattr(entry, "show", None) or getattr(tracker, "show", None)
    if item.media_type in (MediaTypes.SEASON.value, MediaTypes.EPISODE.value):
        query = {"media_type": MediaTypes.TV.value, "media_id": item.media_id, "source": item.source}
        if item.season_number:
            query["season_number"] = item.season_number
    elif item.media_type == MediaTypes.TV.value:
        query = {"media_type": MediaTypes.TV.value, "media_id": item.media_id, "source": item.source}
    elif item.media_type == MediaTypes.PODCAST.value and show is not None:
        query = {"media_type": MediaTypes.PODCAST.value, "podcast_show": show.id}
    else:
        query = {"media_type": item.media_type, "media_id": item.media_id, "source": item.source}
    if item.media_type in (MediaTypes.GAME.value, MediaTypes.BOARDGAME.value):
        query["logging_style"] = "sessions"
    return f"{reverse('history')}?{urlencode(query)}"


def _next_episode_url(request, entry) -> str:
    """The card's Next ep link, with the user's quick update preference on."""
    if request.user.quick_season_update_mobile not in ("next_episode", "both"):
        return ""
    if entry.item.media_type not in _NEXT_EPISODE_TYPES:
        return ""
    return str(app_tags.next_episode_url(entry.item, entry) or "")


def _card(request, entry, current_sort, table=None, kind="item") -> dict:
    if kind == "artist":
        card = _tracker_card(request, entry, entry.artist, current_sort)
    elif kind == "album":
        card = _tracker_card(request, entry, entry.album, current_sort)
    else:
        card = _grid_card(request, entry, current_sort)
        card["history_url"] = _history_url(entry)
        card["next_episode_url"] = _next_episode_url(request, entry)
    card["shape"] = "square" if card["media_type"] in _SQUARE_TYPES else "poster"
    card["repeats"] = entry.repeats if _shows_repeats(entry, request.user) else None
    card["cells"] = table.cells(entry) if table else []
    return card


def _tracker_card(request, tracker, target, current_sort) -> dict:
    """An artist or album card (artist_grid_items.html, album_list_grid_items.html)."""
    from django.urls import reverse

    from users.templatetags.user_tags import user_date_format

    user = request.user
    is_artist = target is getattr(tracker, "artist", None)
    image = target.image or settings.IMG_NONE
    status = tracker.status or None
    if is_artist:
        title = target.name
        url = app_tags.music_artist_url(target)
        subtitle = str(app_tags.media_status_readable(status)) if status else ""
        history = f"{reverse('history')}?artist={target.id}"
        release = getattr(tracker, "first_release_date", None)
    else:
        title = target.title
        url = app_tags.music_album_url(target)
        artist = getattr(target, "artist", None)
        subtitle = artist.name if artist else ""
        history = ""
        release = target.release_date
    dates = {
        "release_date": release,
        "date_added": tracker.created_at,
        "end_date": getattr(tracker, "end_date", None),
        "start_date": getattr(tracker, "start_date", None),
    }
    if current_sort in dates:
        detail = user_date_format(dates[current_sort], user) or ""
    elif current_sort == "score" and tracker.score:
        detail = app_tags.score_display(tracker.score, user)
    else:
        detail = ""
    return {
        "key": target.id,
        "media_type": MediaTypes.MUSIC.value,
        "title": title,
        "url": url,
        "poster": app_tags.image_url(image),
        "poster_srcset": "",
        "status": status,
        "progress": None,
        "subtitle": subtitle,
        "detail": str(detail),
        "history_url": history,
        "next_episode_url": "",
    }


def _grid_card(request, entry, current_sort) -> dict:
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


# Table cells the web draws from the card (image, title) or as lists (genres,
# tags); every other column is the page's own cell template, as text.
_CARD_COLUMNS = frozenset({"image", "title", "artist_name", "album_title"})
_SCORE_COLUMNS = frozenset({"score", "album_score"})
_LIST_COLUMNS = frozenset({"genres", "tags"})
_CELL_NOTE = re.compile(r'<div class="text-xs[^"]*"[^>]*>(.*?)</div>', re.DOTALL)
_EMPTY_CELL = frozenset({"", "-", "--"})


def _align(column) -> str:
    return "center" if "text-center" in column.th_classes else "start"


def _role(key) -> str:
    if key == "image":
        return "image"
    if key in _CARD_COLUMNS:
        return "title"
    if key in _SCORE_COLUMNS:
        return "score"
    if key in _LIST_COLUMNS:
        return "list"
    return "text"


def _shows_repeats(entry, user) -> bool:
    """The cell templates' rule for the repeat count and the Latest/Total notes."""
    if (getattr(entry, "repeats", 0) or 0) <= 1:
        return False
    sessions = getattr(user, "game_logging_style", None) == "sessions"
    return not (
        sessions
        and entry.item.media_type in (MediaTypes.GAME.value, MediaTypes.BOARDGAME.value)
    )


def _cell_text(html: str) -> dict:
    """Split a rendered cell into its value and its small note (Latest, Total...)."""
    note_match = _CELL_NOTE.search(html)
    note = _SPACES.sub(" ", strip_tags(note_match.group(1))).strip() if note_match else ""
    main = _CELL_NOTE.sub("", html) if note_match else html
    text = _SPACES.sub(" ", strip_tags(main)).strip()
    return {
        "text": None if text in _EMPTY_CELL else text,
        "note": note or None,
        "items": [],
    }


def _tag_names(user, items) -> dict[int, list[str]]:
    """Return the user's tag names per item id, in one query (the cell reads per row)."""
    from app.models import ItemTag

    names: dict[int, list[str]] = {}
    rows = (
        ItemTag.objects.filter(item__in=items, tag__user=user)
        .order_by("tag__name")
        .values_list("item_id", "tag__name")
    )
    for item_id, name in rows:
        names.setdefault(item_id, []).append(name)
    return names


class _Table:
    """The page's table layout: its visible columns and each row's cells."""

    def __init__(self, request, context, entries, media_type):
        from django.template import Context
        from django.template.loader import get_template

        from app.columns import resolve_columns

        self.user = request.user
        self.media_type = media_type
        self.columns = resolve_columns(
            media_type, context["current_sort"], self.user, context.get("table_type", "media")
        )
        self._templates = {
            column.key: get_template(column.cell_template).template
            for column in self.columns
            if column.key not in _CARD_COLUMNS | _LIST_COLUMNS
        }
        self._context = Context
        keys = {column.key for column in self.columns}
        self._tags = (
            _tag_names(self.user, [entry.item for entry in entries])
            if "tags" in keys and context.get("table_type", "media") == "media"
            else {}
        )

    def header(self) -> list[dict]:
        return [
            {
                "key": column.key,
                "label": str(_(column.label)) if column.label else "",
                "align": _align(column),
                "role": _role(column.key),
            }
            for column in self.columns
        ]

    def cells(self, entry) -> list[dict]:
        cells = []
        for column in self.columns:
            if column.key in _CARD_COLUMNS:
                continue
            if column.key == "genres":
                cell = {"text": None, "note": None, "items": list(entry.item.genres or [])}
            elif column.key == "tags":
                cell = {"text": None, "note": None, "items": self._tags.get(entry.item.id, [])}
            else:
                html = self._templates[column.key].render(
                    self._context(
                        {
                            "media": entry,
                            "user": self.user,
                            "media_type": self.media_type,
                            "MediaTypes": MediaTypes,
                        }
                    )
                )
                cell = _cell_text(html)
            cells.append({"key": column.key, **cell})
        return cells


def _column_config(config) -> list[dict]:
    return [
        {"key": column["key"], "label": str(_(column["label"])), "visible": column["visible"]}
        for column in config or []
    ]


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


# The filter menu's single-value filters: (query parameter, context key).
_FILTER_VALUES = (
    ("rating", "current_rating"),
    ("collection", "current_collection"),
    ("progress", "current_progress"),
    ("genre", "current_genre"),
    ("implied_genre", "current_implied_genre"),
    ("year", "current_year"),
    ("completed_date_from", "current_completed_date_from"),
    ("completed_date_to", "current_completed_date_to"),
    ("completed_date_within", "current_completed_date_within"),
    ("completed_date_within_unit", "current_completed_date_within_unit"),
    ("release", "current_release"),
    ("source", "current_source"),
    ("media_status", "current_media_status"),
    ("language", "current_language"),
    ("country", "current_country"),
    ("platform_mode", "current_platform_mode"),
    ("origin", "current_origin"),
    ("format", "current_format"),
    ("author", "current_author"),
    ("provider", "current_provider"),
    ("tag_mode", "current_tag_mode"),
)
# Option lists the menu shows; a pane shows when it has options or its
# show_ flag is on, as filter_menu.html decides.
_OPTION_LISTS = (
    "genres",
    "implied_genres",
    "years",
    "sources",
    "media_statuses",
    "languages",
    "countries",
    "platforms",
    "origins",
    "formats",
    "authors",
    "providers",
    "all_providers",
    "relative_date_units",
)
_SHOW_FLAGS = (
    "show_progress",
    "show_languages",
    "show_countries",
    "show_platforms",
    "show_origins",
    "show_formats",
    "show_authors",
    "show_providers",
)


def _option(value) -> dict:
    if isinstance(value, dict):
        return {"value": str(value.get("value", "")), "label": str(value.get("label", ""))}
    return {"value": str(value), "label": str(value)}


def _filters(context) -> dict:
    """Return the filter menu's current values (the page's ``current_*``)."""
    values = {key: str(context.get(name) or "") for key, name in _FILTER_VALUES}
    values["platforms"] = [str(value) for value in context.get("current_platform_values") or []]
    values["tags"] = [str(value) for value in context.get("current_tag") or []]
    return values


def _filter_options(context) -> dict:
    """Return the filter menu's options (the page's ``filter_data``)."""
    data = context.get("filter_data") or {}
    options = {name: [_option(value) for value in data.get(name) or []] for name in _OPTION_LISTS}
    counts = data.get("tag_counts") or {}
    options["tags"] = [
        {"value": str(name), "label": str(name), "count": int(counts.get(name, 0))}
        for name in data.get("tags") or []
    ]
    options.update({flag: bool(data.get(flag)) for flag in _SHOW_FLAGS})
    return options


def _bulk(context) -> dict | None:
    """Bulk select's menus (bulk_selection_toolbar.html), where the page offers it."""
    data = context.get("bulk_action_data") if context.get("enable_bulk_select") else None
    if not data:
        return None
    return {
        "statuses": [{"value": str(s["value"]), "label": str(s["label"])} for s in data["statuses"]],
        "lists": [{"value": str(row["id"]), "label": str(row["label"])} for row in data["lists"]],
        "tags": [str(tag) for tag in data["tags"]],
    }


def _entry_grouping(user, media_type) -> dict | None:
    from app.media_list_entry_grouping import preference_field, show_separate_entries

    if preference_field(media_type) is None:
        return None
    return {"enabled": show_separate_entries(user, media_type)}


def build_library_screen(request, media_type) -> dict:
    """Return the Library page for ``media_type`` as the web screen reads it.

    The page's view runs the list inside the user's entry grouping ("Show
    matching entries separately"), so this does too.
    """
    from app.media_list_entry_grouping import (
        entry_grouping_mode,
        preference_field,
        show_separate_entries,
    )

    mode = (
        show_separate_entries(request.user, media_type) if preference_field(media_type) else None
    )
    with entry_grouping_mode(mode):
        return _build_library_screen(request, media_type)


def _build_library_screen(request, media_type) -> dict:
    from app.media_list_views import build_media_list_context

    context, layout, _resolved = build_media_list_context(request, media_type)
    page = context["media_list"]
    entries = list(page)
    if context.get("is_artist_list"):
        kind = "artist"
    elif context.get("is_album_list"):
        kind = "album"
    else:
        kind = "item"
    table = _Table(request, context, entries, media_type) if layout == "table" else None
    user = request.user
    library = app_tags.ct_library_types(user)
    views = []
    if library["tv_seasons"] and media_type in (MediaTypes.TV.value, MediaTypes.SEASON.value):
        views = [
            {"media_type": MediaTypes.TV.value, "label": "Shows"},
            {"media_type": MediaTypes.SEASON.value, "label": "Seasons"},
        ]
    current_sort = context["current_sort"]
    if kind == "item":
        app_tags.ct_prefetch_posters(entries, "item")
    subviews = _SUBVIEWS.get(media_type, ())
    return {
        "media_type": media_type,
        "title": str(app_tags.media_type_readable_plural(media_type)),
        "count": page.paginator.count if getattr(page, "paginator", None) else len(page),
        "in_progress": app_tags.ct_library_in_progress(user, media_type) or 0,
        "views": views,
        "subviews": [{"value": value, "label": label} for value, label in subviews],
        "subview": str(context.get("current_subview") or (subviews[0][0] if subviews else "")),
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
        "filters": _filters(context),
        "filter_options": _filter_options(context),
        "page": page.number if hasattr(page, "number") else 1,
        "has_next": bool(getattr(page, "has_next", lambda: False)()),
        "layout": "table" if table else "grid",
        "columns": table.header() if table else [],
        "column_config": _column_config(context.get("column_config")) if table else [],
        "column_defaults": _column_config(context.get("default_column_config"))
        if table
        else [],
        "bulk": _bulk(context),
        "entry_grouping": _entry_grouping(user, media_type),
        "results": [_card(request, entry, current_sort, table, kind) for entry in entries],
    }


class LibraryCardProgressSerializer(serializers.Serializer):
    """The inset progress line."""

    percent = serializers.IntegerField()
    paused = serializers.BooleanField()


class LibraryCellSerializer(serializers.Serializer):
    """One table cell, as the page's cell template shows it."""

    key = serializers.CharField(help_text="The column key.")
    text = serializers.CharField(allow_null=True, help_text="The value; null for the page's dash.")
    note = serializers.CharField(
        allow_null=True, help_text="The small line under it (Latest, Total, Earliest, Remaining)."
    )
    items = serializers.ListField(
        child=serializers.CharField(), help_text="Genres or tag names, for those columns."
    )


class LibraryColumnSerializer(serializers.Serializer):
    """A visible table column, in order."""

    key = serializers.CharField()
    label = serializers.CharField(allow_blank=True)
    align = serializers.ChoiceField(choices=["start", "center"])
    role = serializers.ChoiceField(
        choices=["image", "title", "score", "list", "text"],
        help_text="How the web draws it: the card's poster or title, a score, a list or text.",
    )


class LibraryColumnConfigSerializer(serializers.Serializer):
    """A column the user can show or hide (the page's column menu)."""

    key = serializers.CharField()
    label = serializers.CharField()
    visible = serializers.BooleanField()


class LibraryCardSerializer(serializers.Serializer):
    """A Library poster card, or a table row."""

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
    repeats = serializers.IntegerField(
        allow_null=True, help_text="Times repeated, when the table's title shows it."
    )
    shape = serializers.ChoiceField(
        choices=["poster", "square"], help_text="Music and podcasts draw square art."
    )
    history_url = serializers.CharField(
        allow_blank=True, help_text="The card menu's History link (Django)."
    )
    next_episode_url = serializers.CharField(
        allow_blank=True,
        help_text="The Next ep link, with the user's quick update preference on.",
    )
    cells = LibraryCellSerializer(
        many=True, help_text="The row's cells after image and title; empty in the grid."
    )


class LibraryChoiceSerializer(serializers.Serializer):
    """A sort or status the page offers."""

    value = serializers.CharField()
    label = serializers.CharField()


class LibraryViewSerializer(serializers.Serializer):
    """Shows or Seasons, when both TV views are on."""

    media_type = serializers.CharField()
    label = serializers.CharField()


class LibraryFiltersSerializer(serializers.Serializer):
    """The filter menu's current values, named as the page's query parameters."""

    rating = serializers.CharField(help_text="all, rated or not_rated.")
    collection = serializers.CharField(help_text="all, collected or not_collected.")
    progress = serializers.CharField(help_text="all, not_caught_up or caught_up.")
    genre = serializers.CharField(allow_blank=True)
    implied_genre = serializers.CharField(allow_blank=True)
    year = serializers.CharField(allow_blank=True, help_text="A release year, or unknown.")
    completed_date_from = serializers.CharField(allow_blank=True)
    completed_date_to = serializers.CharField(allow_blank=True)
    completed_date_within = serializers.CharField(allow_blank=True)
    completed_date_within_unit = serializers.CharField(allow_blank=True)
    release = serializers.CharField(help_text="all, released or not_released.")
    source = serializers.CharField(allow_blank=True)
    media_status = serializers.CharField(allow_blank=True)
    language = serializers.CharField(allow_blank=True)
    country = serializers.CharField(allow_blank=True)
    platforms = serializers.ListField(child=serializers.CharField())
    platform_mode = serializers.CharField(help_text="or, and or not.")
    origin = serializers.CharField(allow_blank=True)
    format = serializers.CharField(allow_blank=True)
    author = serializers.CharField(allow_blank=True)
    provider = serializers.CharField(allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField())
    tag_mode = serializers.CharField(help_text="or, and or not.")


class LibraryTagOptionSerializer(LibraryChoiceSerializer):
    """A tag, with how many titles in this list carry it."""

    count = serializers.IntegerField()


class LibraryFilterOptionsSerializer(serializers.Serializer):
    """The filter menu's options; a pane shows when it has options or its flag is on."""

    genres = LibraryChoiceSerializer(many=True)
    implied_genres = LibraryChoiceSerializer(many=True)
    years = LibraryChoiceSerializer(many=True)
    sources = LibraryChoiceSerializer(many=True)
    media_statuses = LibraryChoiceSerializer(many=True)
    languages = LibraryChoiceSerializer(many=True)
    countries = LibraryChoiceSerializer(many=True)
    platforms = LibraryChoiceSerializer(many=True)
    origins = LibraryChoiceSerializer(many=True)
    formats = LibraryChoiceSerializer(many=True)
    authors = LibraryChoiceSerializer(many=True)
    providers = LibraryChoiceSerializer(many=True)
    all_providers = LibraryChoiceSerializer(many=True)
    relative_date_units = LibraryChoiceSerializer(many=True)
    tags = LibraryTagOptionSerializer(many=True)
    show_progress = serializers.BooleanField()
    show_languages = serializers.BooleanField()
    show_countries = serializers.BooleanField()
    show_platforms = serializers.BooleanField()
    show_origins = serializers.BooleanField()
    show_formats = serializers.BooleanField()
    show_authors = serializers.BooleanField()
    show_providers = serializers.BooleanField()


class LibraryBulkSerializer(serializers.Serializer):
    """Bulk select's menus: statuses, the user's editable lists, their tags."""

    statuses = LibraryChoiceSerializer(many=True)
    lists = LibraryChoiceSerializer(many=True, help_text="Value is the list id.")
    tags = serializers.ListField(child=serializers.CharField())


class LibraryEntryGroupingSerializer(serializers.Serializer):
    """The View settings' "Show matching entries separately"."""

    enabled = serializers.BooleanField()


class LibraryScreenSerializer(serializers.Serializer):
    """One page of the Library for a media type, with its menus' state."""

    media_type = serializers.CharField()
    title = serializers.CharField()
    count = serializers.IntegerField(help_text="Titles matching the filters, all pages.")
    in_progress = serializers.IntegerField()
    views = LibraryViewSerializer(many=True)
    subviews = LibraryChoiceSerializer(
        many=True, help_text="Music: artists, albums, tracks. Comics: comics, issues."
    )
    subview = serializers.CharField(allow_blank=True, help_text="Send as `subview`.")
    sort = serializers.CharField()
    direction = serializers.CharField(help_text='"asc" or "desc".')
    sorts = LibraryChoiceSerializer(many=True)
    statuses = serializers.ListField(
        child=serializers.CharField(), help_text="Selected statuses; empty for all."
    )
    status_choices = LibraryChoiceSerializer(many=True)
    search = serializers.CharField(allow_blank=True)
    filters = LibraryFiltersSerializer()
    filter_options = LibraryFilterOptionsSerializer()
    page = serializers.IntegerField()
    has_next = serializers.BooleanField()
    layout = serializers.ChoiceField(
        choices=["grid", "table"], help_text="The user's saved layout for this type."
    )
    columns = LibraryColumnSerializer(many=True, help_text="Table only; image and title first.")
    column_config = LibraryColumnConfigSerializer(
        many=True, help_text="Table only: the columns the user can hide, in order."
    )
    column_defaults = LibraryColumnConfigSerializer(
        many=True, help_text="Table only: the menu's Reset to defaults."
    )
    bulk = LibraryBulkSerializer(
        allow_null=True, help_text="Null where the page has no bulk select (artists, albums)."
    )
    entry_grouping = LibraryEntryGroupingSerializer(
        allow_null=True, help_text="Null for types without the setting."
    )
    results = LibraryCardSerializer(many=True)
