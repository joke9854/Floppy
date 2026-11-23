"""The Statistics screen's per-type Activity Overviews (v2 P4-H3).

The Django page renders nine overview templates
(templates/app/components/statistics/*_activity_overview.html and
reading_consumption_section.html); the web draws one component, so each is
written here as charts (single-series, by year, month or day) and ranked
lists, with the captions the templates write.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from app.templatetags import app_tags

_ORDER = ("tv", "anime", "manga", "movie", "game", "book", "comic", "music", "podcast")
_FLAGS = {
    "manga": "manga_enabled",
    "book": "book_enabled",
    "comic": "comic_enabled",
    "music": "music_enabled",
    "podcast": "podcast_enabled",
}
_EYEBROWS = {
    "tv": "TV Shows",
    "anime": "Anime",
    "manga": "Manga",
    "movie": "Movies",
    "game": "Video Games",
    "book": "Books",
    "comic": "Comics",
    "music": "Music",
    "podcast": "Podcast",
}
_EMPTY = {
    "tv": "No episode plays available for this range.",
    "anime": "No episode plays available for this range.",
    "movie": "No movie plays available for this range.",
    "game": "No game hours available for this range.",
    "music": "No artist data available.",
    "podcast": "No podcast plays available for this range.",
}


def _chart(title, chart, empty, color="#6366f1") -> dict:
    chart = chart or {}
    datasets = chart.get("datasets") or []
    values = [float(value or 0) for value in (datasets[0].get("data") if datasets else []) or []]
    dataset_color = datasets[0].get("background_color") or datasets[0].get("backgroundColor") if datasets else None
    return {
        "title": title,
        "labels": [str(label) for label in chart.get("labels") or []],
        "values": values,
        "color": str(dataset_color) if isinstance(dataset_color, str) else color,
        "empty": empty,
    }


def _image(value) -> str:
    """Return the image's URL; "" for none (any size of TMDB's none.jpg)."""
    if not value or str(value).endswith("/none.jpg"):
        return ""
    return str(app_tags.image_url(value) or "")


def _media_entry(media, caption: str) -> dict:
    item = getattr(media, "item", None)
    image = getattr(item, "image", None)
    return {
        "title": str(app_tags.display_title(item, getattr(media, "user", None)) or getattr(item, "title", "") or ""),
        "href": str(app_tags.media_url(item) or "") if item else "",
        "image": _image(image),
        "caption": caption,
    }


def _list(title, entries, empty) -> dict:
    return {"title": title, "items": [entry for entry in entries if entry], "empty": empty}


def _top_rated(context, media_type) -> dict:
    entries = []
    user = context.get("user")
    for media in context.get(f"top_rated_{media_type}") or []:
        # The template prints the score on the user's scale (score_display).
        score = getattr(media, "aggregated_score", None)
        if score is None:
            score = getattr(media, "score", None)
        caption = f"{chr(0x2605)} {app_tags.score_display(score, user)}" if score is not None else ""
        entries.append(_media_entry(media, caption))
    return _list(_("Top Rated"), entries, _("No ratings yet."))


def _played_caption(entry, unit: str) -> str:
    duration = str(entry.get("formatted_duration") or "")
    if unit == "episode":
        count = int(entry.get("episode_count") or 0)
        return ngettext("%(value_1)s · %(value_2)s episode", "%(value_1)s · %(value_2)s episodes", count) % {
            "value_1": duration,
            "value_2": count,
        }
    if unit == "play":
        count = int(entry.get("play_count") or entry.get("plays") or 0)
        return ngettext("%(value_1)s · %(value_2)s play", "%(value_1)s · %(value_2)s plays", count) % {
            "value_1": duration,
            "value_2": count,
        }
    return duration


def _most_played(context, media_type, unit) -> dict:
    entries = [
        _media_entry(entry.get("media"), _played_caption(entry, unit))
        for entry in (context.get("top_played") or {}).get(media_type) or []
        if isinstance(entry, dict) and entry.get("media") is not None
    ]
    return _list(_("Most Played"), entries, _EMPTY.get(media_type, ""))


def _safe_url(view_name, *args, **kwargs) -> str:
    try:
        return reverse(view_name, args=args, kwargs=kwargs or None)
    except NoReverseMatch:
        return ""


def _music(context, consumption) -> list[dict]:
    def plays(entry):
        count = int(entry.get("plays") or 0)
        return ngettext("%(value_1)s · %(value_2)s play", "%(value_1)s · %(value_2)s plays", count) % {
            "value_1": entry.get("formatted_duration") or "",
            "value_2": count,
        }

    def named(entries, title_key, href, image_key="image"):
        return [
            {
                "title": str(entry.get(title_key) or ""),
                "href": href(entry),
                "image": _image(entry.get(image_key)),
                "caption": plays(entry),
            }
            for entry in entries or []
            if isinstance(entry, dict)
        ]

    artists = consumption.get("top_artists") or []
    albums = consumption.get("top_albums") or []
    tracks = consumption.get("top_tracks") or []
    decades = consumption.get("top_decades") or []
    countries = consumption.get("top_countries") or []
    return [
        _list(_("Top %(value_1)s Artists") % {"value_1": len(artists)},
              named(artists, "name", lambda e: str(app_tags.music_artist_url(e) or "")), _("No artist data available.")),
        _list(_("Top %(value_1)s Albums") % {"value_1": len(albums)},
              named(albums, "title", lambda e: str(app_tags.music_album_url(e) or "")), _("No album data available.")),
        _list(_("Top %(value_1)s Tracks") % {"value_1": len(tracks)},
              named(tracks, "title", lambda e: str(app_tags.music_album_url(e) or ""), "album_image"),
              _("No track data available.")),
        _list(_("Top %(value_1)s Decades") % {"value_1": len(decades)},
              named(decades, "label", lambda e: ""), _("No decade data available.")),
        _list(_("Top %(value_1)s Countries") % {"value_1": len(countries)},
              named(countries, "name", lambda e: ""), _("No country data available.")),
    ]


def _podcast(consumption) -> list[dict]:
    def entry_href(entry):
        if entry.get("podcast_uuid"):
            return _safe_url(
                "media_details",
                source="pocketcasts",
                media_type="podcast",
                media_id=entry["podcast_uuid"],
                title=slugify(entry.get("slug") or entry.get("title") or "") or "podcast",
            )
        if entry.get("show_id"):
            return _safe_url("podcast_show_detail", entry["show_id"])
        return ""

    def entries(items, caption):
        return [
            {
                "title": str(entry.get("title") or ""),
                "href": entry_href(entry),
                "image": _image(entry.get("image")),
                "caption": caption(entry),
            }
            for entry in items or []
            if isinstance(entry, dict)
        ]

    def plays(entry):
        count = int(entry.get("plays") or 0)
        return ngettext("%(value_1)s play", "%(value_1)s plays", count) % {"value_1": count}

    def listened(entry):
        count = int(entry.get("plays") or 0)
        return ngettext("%(value_1)s · %(value_2)s play", "%(value_1)s · %(value_2)s plays", count) % {
            "value_1": entry.get("formatted_duration") or "",
            "value_2": count,
        }

    return [
        _list(_("Most Played"), entries(consumption.get("most_played"), plays), _("No episode data available.")),
        _list(_("Most Listened"), entries(consumption.get("most_listened"), listened), _("No show data available.")),
        _list(
            _("Longest Episodes"),
            entries(consumption.get("longest_episodes"), lambda e: str(e.get("formatted_duration") or "")),
            _("No episode data available."),
        ),
    ]


def _count(value) -> int:
    if isinstance(value, (set, list, tuple)):
        return len(value)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _reading_count(noun, value) -> str:
    """Return " · N books" (comics, manga) as the reading section writes it; "" for none."""
    count = _count(value)
    if not count:
        return ""
    if noun == "book":
        text = ngettext("· %(value_1)s book", "· %(value_1)s books", count)
    elif noun == "comic":
        text = ngettext("· %(value_1)s comic", "· %(value_1)s comics", count)
    else:
        text = "· %(value_1)s manga"
    return " " + text % {"value_1": count}


def _reading(context, media_type, consumption, media_name: str) -> tuple[list, list]:
    unit = str(consumption.get("unit_name") or "")
    completion = str(consumption.get("completion_label") or "")
    charts = []
    if context.get("show_year_charts"):
        charts.append(_chart(
            _("%(value_1)s by Year") % {"value_1": completion},
            (consumption.get("completion_charts") or {}).get("by_year"),
            _("No yearly completion data available."),
        ))
    charts.append(_chart(
        _("%(value_1)s Released by Year") % {"value_1": media_name},
        consumption.get("release_chart"),
        _("No release data available."),
    ))
    charts.append(_chart(
        _("Completed %(value_1)ss") % {"value_1": unit},
        consumption.get("completed_length_chart"),
        _("No completion length data available."),
    ))
    noun = {"book": "book", "comic": "comic"}.get(media_type)
    most_read = []
    for entry in consumption.get("top_items") or []:
        if not isinstance(entry, dict) or entry.get("media") is None:
            continue
        most_read.append(_media_entry(
            entry["media"],
            f"{entry.get('formatted_units') or ''}{_reading_count(noun, entry.get('entry_count'))}",
        ))
    lists = [_list(_("Most Read"), most_read, _("No reading data available."))]
    authors = consumption.get("top_authors") or []
    if media_type == "book":
        lists.append(_list(
            _("Top %(value_1)s Authors") % {"value_1": len(authors)},
            [
                {
                    "title": str(author.get("name") or ""),
                    "href": (
                        _safe_url(
                            "person_detail",
                            source=author["source"],
                            person_id=author["person_id"],
                            name=slugify(author.get("name") or "") or "person",
                        )
                        if author.get("source") and author.get("person_id")
                        else ""
                    ),
                    "image": _image(author.get("image")),
                    "caption": ngettext(
                        "%(value_1)s · %(value_2)s book",
                        "%(value_1)s · %(value_2)s books",
                        _count(author.get("titles")),
                    )
                    % {"value_1": author.get("formatted_units") or "", "value_2": _count(author.get("titles"))},
                }
                for author in authors
                if isinstance(author, dict)
            ],
            _("No author data available."),
        ))
    history = reverse("history")

    def genre_href(name):
        query = {"genre": name, "media_type": media_type}
        for key in ("start_date_str", "end_date_str"):
            value = context.get(key)
            if value and value != "all":
                query["start-date" if key == "start_date_str" else "end-date"] = value
        return f"{history}?{urlencode(query)}"

    lists.append(_list(
        _("Top Genres"),
        [
            {
                "title": str(genre.get("name") or ""),
                "href": genre_href(str(genre.get("name") or "")),
                "image": "",
                "caption": f"{genre.get('formatted_units') or ''}{_reading_count(noun, genre.get('titles'))}",
            }
            for genre in consumption.get("top_genres") or []
            if isinstance(genre, dict)
        ],
        _("No genre data available."),
    ))
    lists.append(_top_rated(context, media_type))
    return charts, lists


def build_overviews(context, user) -> list[dict]:
    """Return the visible per-type Activity Overviews, in the page's order."""
    year_charts = bool(context.get("show_year_charts"))
    overviews = []
    for media_type in _ORDER:
        flag = _FLAGS.get(media_type)
        if flag and not getattr(user, flag, False):
            continue
        consumption = context.get(f"{media_type}_consumption") or {}
        if not consumption.get("has_data"):
            continue
        charts_data = consumption.get("charts") or {}
        charts: list[dict] = []
        lists: list[dict] = []
        if media_type in ("tv", "anime"):
            if year_charts:
                charts.append(_chart(_("Episode Plays by Year"), charts_data.get("by_year"), _EMPTY[media_type]))
            lists = [_most_played(context, media_type, "episode"), _top_rated(context, media_type)]
        elif media_type == "movie":
            if year_charts:
                charts.append(_chart(_("Movie Plays by Year"), charts_data.get("by_year"), _EMPTY["movie"]))
            lists = [_most_played(context, "movie", "play"), _top_rated(context, "movie")]
        elif media_type == "game":
            if year_charts:
                charts.append(_chart(_("Game Hours by Year"), charts_data.get("by_year"), _EMPTY["game"]))
            charts.append(_chart(_("Game Hours by Month"), charts_data.get("by_month"), _("No monthly game hours recorded.")))
            charts.append(_chart(
                _("Average Daily Playtime"), charts_data.get("by_daily_average"), _("No daily average data available.")
            ))
            platforms = []
            for platform in consumption.get("platform_breakdown") or []:
                games = int(platform.get("games") or 0)
                platforms.append({
                    "title": str(platform.get("name") or ""),
                    "href": "",
                    "image": "",
                    "caption": ngettext("%(value_1)s · %(value_2)s game", "%(value_1)s · %(value_2)s games", games)
                    % {"value_1": platform.get("formatted_hours") or "", "value_2": games},
                })
            lists = [
                _most_played(context, "game", "duration"),
                _list(_("Top Platforms"), platforms, _("No platform data available.")),
            ]
        elif media_type == "music":
            if year_charts:
                charts.append(_chart(_("Music Plays by Year"), charts_data.get("by_year"), _EMPTY["music"]))
            lists = _music(context, consumption)
        elif media_type == "podcast":
            if year_charts:
                charts.append(_chart(_("Podcast Plays by Year"), charts_data.get("by_year"), _EMPTY["podcast"]))
            lists = _podcast(consumption)
        else:
            charts, lists = _reading(context, media_type, consumption, _(_EYEBROWS[media_type]))
        overviews.append({
            "media_type": media_type,
            "eyebrow": _(_EYEBROWS[media_type]),
            "charts": charts,
            "lists": lists,
        })
    return overviews


def build_board_games(context) -> list[dict]:
    """Return the board games Most Played grid (statistics.html)."""
    return [
        _media_entry(entry.get("media"), str(entry.get("formatted_duration") or ""))
        for entry in (context.get("top_played") or {}).get("boardgame") or []
        if isinstance(entry, dict) and entry.get("media") is not None
    ]
