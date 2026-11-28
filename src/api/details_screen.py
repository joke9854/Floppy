"""The web detail page's data (v2 P4-C1): the Django movie and show page, as JSON.

`app.media_details_views.build_media_details_context` is the page's own
builder, and `app.season_details_views.build_season_details_context` the
show page's episode list, so this shows exactly what /details/... shows. The
page renders in two phases and so does this: the shell reads only caches;
the secondary phase fetches what is missing and fills the sections below the
hero. Values come from the template helpers the CineTrack v2 templates use
(`ct/detail_hero.html`, `ct/detail_secondary.html`, `ct/episode_row.html`).

Like the page, a GET can write (metadata it resolves, refreshes it queues),
which is why the route takes the session or the account token only.
"""

from __future__ import annotations

from urllib.parse import parse_qs, quote

from django.conf import settings
from django.template.defaultfilters import floatformat
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags
from rest_framework import serializers

from app.models import MediaTypes, Sources, Status
from app.templatetags import app_tags
from users.appearance import resolved_detail_layouts
from users.templatetags import user_tags

from .home_screen import HomeCheckTargetSerializer

# The types whose page the web also draws (P4-L1): books, manga, games, comics
# and board games share one set of sections beside the movie and show page.
L1_TYPES = (
    MediaTypes.MANGA.value,
    MediaTypes.GAME.value,
    MediaTypes.BOOK.value,
    MediaTypes.COMIC.value,
    MediaTypes.BOARDGAME.value,
)
# Anime joins in P4-L3a: grouped anime (TMDB, TVDB) reads like a show, flat MAL
# anime lists its mapped episodes read-only.
DETAIL_SCREEN_TYPES = (
    MediaTypes.MOVIE.value,
    MediaTypes.TV.value,
    MediaTypes.ANIME.value,
    *L1_TYPES,
)
_SERIES_TYPES = (MediaTypes.TV.value, MediaTypes.ANIME.value)
DETAIL_PARTS = ("shell", "secondary", "season")

# The v2 sections in the order ct/detail_secondary.html renders them, with
# the layout zone each one's `detail_section_attrs` names. The v2 sections are
# a block, not a flex box, so the layout's order does not move them: a
# section the user's layout leaves out is hidden.
_SECTIONS = (
    ("episodes", "content"),
    ("history", "sidebar"),
    ("related", "content"),
    ("cast", "content"),
    ("recommendations", "content"),
    ("details", "sidebar"),
)
# The extended order for the L1 types (the layout family still filters it).
_SECTIONS_L1 = (
    ("episodes", "content"),
    ("history", "sidebar"),
    ("related", "content"),
    ("cast", "content"),
    ("recommendations", "content"),
    ("game_lengths", "content"),
    ("details", "sidebar"),
    ("genres", "sidebar"),
    ("studios", "sidebar"),
)
# Information grid keys the template leaves out.
_INFO_SKIPPED = {"themes", "format", "last_air_date", "seasons", "episodes"}
_INFO_SKIPPED_L1 = _INFO_SKIPPED - {"format"}


def _text(value) -> str:
    return "" if value is None else str(value)


def _image(value, size: str) -> str:
    return app_tags.image_url(app_tags.tmdb_size(value or settings.IMG_NONE, size))


def _backdrop(media, *, allow_network: bool) -> str | None:
    """Return the hero backdrop: fanart.tv's background, else the provider's."""
    fanart = app_tags.ct_fanart(media, allow_network=allow_network) or {}
    return fanart.get("background") or app_tags.ct_detail_backdrop(
        media, allow_network=allow_network
    )


def _fanart(media, *, allow_network: bool) -> dict:
    """Return fanart.tv's poster and title logo (ct/detail_fanart.html), or None each."""
    fanart = app_tags.ct_fanart(media, allow_network=allow_network) or {}
    return {
        "fanart_poster": app_tags.image_url(fanart["poster"]) if fanart.get("poster") else None,
        "logo": app_tags.image_url(fanart["logo"]) if fanart.get("logo") else None,
    }


def _links(context) -> list[dict]:
    """Return the links popover's sections (detail_action_buttons.html)."""
    return [
        {
            "title": _text(section.get("title")),
            "links": [
                {
                    "label": _text(entry.get("label")),
                    "url": _text(entry.get("url")),
                    "logo": app_tags.image_url(entry["logo_src"]) if entry.get("logo_src") else None,
                    "fallback": _text(entry.get("fallback_text"))[:4],
                }
                for entry in section.get("entries") or []
                if entry.get("url")
            ],
        }
        for section in context.get("detail_link_sections") or []
    ]


def _watch_on(watch_on) -> dict | None:
    """Return the "Watch on" chips: four subscriptions, two rent or buy, the link."""
    if not watch_on:
        return None

    def chip(provider, offer):
        return {
            "name": _text(provider.get("provider_name")),
            "image": app_tags.image_url(provider.get("image")),
            "offer": offer,
        }

    def rent_buy(offers):
        if "rent" in offers and "buy" in offers:
            return "Rent · Buy"
        return "Rent" if "rent" in offers else "Buy"

    return {
        "subscription": [
            chip(p, "Subscription" if "flatrate" in (p.get("offers") or []) else "Free")
            for p in (watch_on.get("subscription") or [])[:4]
        ],
        "rent_buy": [
            chip(p, rent_buy(p.get("offers") or []))
            for p in (watch_on.get("rent_buy") or [])[:2]
        ],
        "link": watch_on.get("link") or None,
    }


def _scores(context) -> list[dict]:
    """Return the score chips' values (detail_score_chips.html), without graphs."""
    media = context["media"]
    scores = []
    if media.get("score_count") is not None and media.get("score") is not None:
        scores.append(
            {
                "key": "provider",
                "label": _text(
                    app_tags.source_readable(context.get("display_provider"))
                ),
                "short": _text(context.get("display_provider")).upper()[:4],
                "rating": _text(media.get("score")),
                "count": media.get("score_count"),
            }
        )
    for key, label in (
        ("trakt_score", "Trakt"),
        ("imdb_score", "IMDb"),
        ("mal_score", "MAL"),
    ):
        score = context.get(key)
        if score and score.get("rating") is not None:
            scores.append(
                {
                    "key": key.removesuffix("_score"),
                    "label": label,
                    "short": label,
                    "rating": _text(score.get("rating")),
                    "count": score.get("rating_count"),
                }
            )
    return scores


def _can_check(source) -> bool:
    """Whether the episode ensure endpoint takes this source (tmdb, manual)."""
    from .helpers import check_source_type

    return check_source_type(MediaTypes.TV.value, source)


def _library_type(media_type, item):
    """Return the bucket a check lands in: an anime page's own, else the row's Item's."""
    if media_type == MediaTypes.ANIME.value:
        return MediaTypes.ANIME.value
    return getattr(item, "library_media_type", None)


def _check_target(target, media_type=MediaTypes.TV.value) -> dict | None:
    if not target or not _can_check(target["source"]):
        return None
    return {
        "source": target["source"],
        "media_id": str(target["media_id"]),
        "season_number": target["season_number"],
        "episode_number": target["episode_number"],
        "library_media_type": MediaTypes.ANIME.value
        if media_type == MediaTypes.ANIME.value
        else target.get("library_media_type"),
    }


def _action(context) -> dict | None:
    """Return the hero's filled button (ct/detail_hero.html)."""
    if context.get("public_view"):
        return None
    media_type = context["media_type"]
    if media_type not in (MediaTypes.MOVIE.value, *_SERIES_TYPES):
        return None
    current = context.get("current_instance")
    status = getattr(current, "status", None)
    if media_type == MediaTypes.MOVIE.value:
        if status == Status.COMPLETED.value:
            return {"kind": "watched", "episode": None}
        if current is None or status == Status.PLANNING.value:
            return {"kind": "mark", "episode": None}
        return None
    if not _can_check(context["media"].get("source")):
        # The ensure endpoint takes tmdb and manual only (flat MAL anime and
        # TVDB shows are read-only here): no mark-next, the Track button stays.
        return (
            {"kind": "completed", "episode": None}
            if status == Status.COMPLETED.value
            else None
        )
    target = app_tags.ct_detail_next_episode(context["media"], current)
    if target:
        return {"kind": "episode", "episode": _check_target(target, media_type)}
    # No named next episode: the page takes the first unwatched aired
    # episode of the season on screen, or stays green when completed.
    return {
        "kind": "completed" if status == Status.COMPLETED.value else "episode",
        "episode": None,
    }


def _meta(context) -> dict:
    media = context["media"]
    media_type = context["media_type"]
    details = media.get("details") or {}
    year = app_tags.release_year(details) or app_tags.release_year(media) or None
    percent = None
    if media_type in _SERIES_TYPES and not context.get("public_view"):
        progress = app_tags.ct_series_progress(media, context.get("current_instance"))
        percent = (progress or {}).get("percent") or None
    progress_text = None
    if media_type in L1_TYPES and not context.get("public_view"):
        subtitle = context.get("activity_subtitle") or {}
        progress_text = _text(subtitle.get("primary_text")) or None
    series = None
    if media_type == MediaTypes.BOOK.value and media.get("series_name"):
        series = _text(media["series_name"])
        if media.get("series_position"):
            series += f" #{floatformat(media['series_position'], '-2')}"
    return {
        "type_label": _text(app_tags.media_type_readable(media_type)),
        "genres": [_text(genre) for genre in (media.get("genres") or [])[:2]],
        "year": _text(year) or None,
        "runtime": _text(details.get("runtime")) or None
        if media_type == MediaTypes.MOVIE.value
        else None,
        "certification": _text(details.get("certification")) or None
        if media_type == MediaTypes.MOVIE.value
        else None,
        "seasons": details.get("seasons") if media_type in _SERIES_TYPES else None,
        "percent": percent,
        "progress": progress_text,
        "series": series,
    }


def build_detail_shell(request, context) -> dict:
    """Return the hero: what the page's shell phase paints first, from caches."""
    media = context["media"]
    user = request.user
    current = context.get("current_instance")
    title = app_tags.display_title(media, user)
    return {
        "media_type": context["media_type"],
        "source": media.get("source"),
        "media_id": str(media.get("media_id")),
        "title": _text(title),
        "page_url": app_tags.media_url(media),
        "poster": _image(media.get("image"), "w500"),
        "poster_srcset": app_tags.tmdb_srcset(media.get("image"), "w342,w500,w780")
        or "",
        "backdrop": _backdrop(media, allow_network=False),
        **_fanart(media, allow_network=False),
        "links": _links(context),
        "meta": _meta(context),
        "scores": _scores(context),
        "my_score": getattr(current, "score", None) if current is not None else None,
        "status": getattr(current, "status", None) or None,
        "action": _action(context),
        "synopsis": strip_tags(_text(media.get("synopsis"))).strip(),
        "watch_on": _watch_on(context.get("watch_on")),
        "track_time": settings.TRACK_TIME,
    }


def _card(entry, user) -> dict:
    """Return a related list's or More Like This's poster card (ct/poster_card.html)."""
    item = entry.get("item") if isinstance(entry, dict) and "item" in entry else entry
    media = entry.get("media") if isinstance(entry, dict) else None
    image = getattr(media, "card_image_override", None) or app_tags.ct_poster(item)
    image = image or settings.IMG_NONE
    released = app_tags._ct_value(item, "release_datetime")
    status = getattr(media, "aggregated_status", None) or getattr(media, "status", None)
    return {
        "media_type": app_tags._ct_value(item, "media_type"),
        "title": _text(app_tags.display_title(item, user)),
        "url": app_tags.media_url(item),
        "poster": _image(image, "w342"),
        "poster_srcset": app_tags.tmdb_srcset(image) or "",
        "subtitle": released.strftime("%Y") if released else "",
        "status": status or None,
    }


def _person(person, media, character_images=None) -> dict:
    """Return a person card (ct/person_card.html); crew cards show the job as role."""
    url = None
    if person.get("person_id") and person.get("name"):
        try:
            url = reverse(
                "person_detail",
                kwargs={
                    "source": media.get("source"),
                    "person_id": person["person_id"],
                    "name": app_tags.slug(person["name"]),
                },
            )
        except NoReverseMatch:
            url = None
    image = person.get("image")
    character = app_tags.ct_character_image(character_images, person)
    return {
        "name": _text(person.get("name")) or "Unknown",
        "role": _text(person.get("role")),
        "image": app_tags.image_url(image)
        if image and image != settings.IMG_NONE
        else None,
        "character_image": app_tags.image_url(character) if character else None,
        "url": url,
    }


def _plays(context, user) -> list[dict]:
    """Your Plays (movies): every entry that is not a plan, newest first."""
    plays = []
    for play in app_tags.ct_plays(context.get("user_medias")):
        if play.end_date:
            when = _text(app_tags.datetime_format(play.end_date, user))
        elif play.start_date:
            when = f"Started {app_tags.datetime_format(play.start_date, user)}"
        else:
            when = "No date"
        done = play.status == Status.COMPLETED.value
        plays.append(
            {
                "status": play.status,
                "label": "Watched"
                if done
                else _text(app_tags.media_status_readable(play.status)),
                "when": when,
                "score": _text(play.score) if play.score is not None else None,
            }
        )
    return plays


def _info(context, user, *, authors=(), studios=()) -> list[dict]:
    """Return the Information grid (the page's labels and date formats)."""
    media = context["media"]
    details = media.get("details") or {}
    skipped = _INFO_SKIPPED_L1 if context["media_type"] in L1_TYPES else _INFO_SKIPPED
    rows = []
    for key, value in details.items():
        if key in skipped or not value:
            continue
        # The linked Authors and Studios rows replace the plain ones.
        if authors and key in (context.get("author_detail_keys") or ()):
            continue
        if studios and key in (context.get("studio_detail_keys") or ()):
            continue
        if key == "first_air_date":
            label = "Aired"
            text = _text(user_tags.user_date_format(value, user))
            last = details.get("last_air_date")
            if last and last != value:
                text += f" – {user_tags.user_date_format(last, user)}"  # noqa: RUF001  # the page's en dash
        else:
            if key == "studios" and context["media_type"] in _SERIES_TYPES:
                label = "Network"
            else:
                label = key.replace("_", " ").title()
            if isinstance(value, (list, tuple)):
                text = ", ".join(
                    _text(app_tags.iso_date_format(v, user)) for v in value
                )
            elif key in ("release_date", "air_date"):
                text = _text(user_tags.user_date_format(value, user))
            else:
                text = _text(value)
        rows.append({"label": label, "value": text})
    return rows


def _sections(user, media_type) -> list[str]:
    """Return the sections the user's detail layout shows, in page order."""
    family = user_tags.detail_layout_family(media_type)
    layouts = resolved_detail_layouts(
        getattr(user, "detail_page_layouts", {}) if user.is_authenticated else {}
    ).get(family, {})
    order = _SECTIONS_L1 if media_type in L1_TYPES else _SECTIONS
    return [key for key, zone in order if key in layouts.get(zone, [])]


def _episode(
    episode,
    show,
    season_number,
    user,
    next_number,
    media_type=MediaTypes.TV.value,
    *,
    read_only=False,
) -> dict:
    history = episode.get("history") or []
    watched = app_tags.watched_count(history)
    history_text = ""
    if history:
        first = history[0]
        if getattr(first, "dropped", False) and watched == 0:
            history_text = "Dropped"
        else:
            history_text = (
                f"Watched {watched} times · last" if watched > 1 else "Watched"
            )
            if getattr(first, "end_date", None):
                history_text += f" {app_tags.datetime_format(first.end_date, user)}"
    number = episode.get("episode_number")
    url = None
    if show.get("source") and show.get("media_id") and number is not None:
        try:
            url = reverse(
                "anime_episode_details"
                if media_type == MediaTypes.ANIME.value
                else "episode_details",
                kwargs={
                    "source": show["source"],
                    "media_id": show["media_id"],
                    "title": app_tags.slug(show.get("title") or ""),
                    "season_number": season_number,
                    "episode_number": number,
                },
            )
        except NoReverseMatch:
            url = None
    image = episode.get("image") or settings.IMG_NONE
    overview = _text(episode.get("overview"))
    show_overview = bool(overview) and (
        bool(history) or not user.hide_episode_overviews
    )
    air_date = episode.get("air_date")
    item = episode.get("item")
    return {
        "episode_number": number,
        "display_number": episode.get("display_episode_number") or number,
        "title": _text(episode.get("title")),
        "still": _image(image, "w300"),
        "still_srcset": app_tags.tmdb_srcset(image, "w185,w300") or "",
        "placeholder": image == settings.IMG_NONE,
        "air_date": _text(user_tags.user_date_format(air_date, user))
        if air_date
        else "Unknown date",
        "aired": bool(air_date) and air_date <= _now(),
        "runtime": _text(episode.get("runtime")) or None,
        "overview": overview if show_overview else "",
        "blurred": bool(user.obfuscate_episodes) and not history,
        "watched": bool(history),
        "history": history_text,
        "is_next": next_number is not None and number == next_number and not history,
        "url": url,
        "check": {
            "source": show.get("source"),
            "media_id": str(show.get("media_id")),
            "season_number": season_number,
            "episode_number": number,
            "library_media_type": _library_type(media_type, item),
        }
        if not read_only
        and episode.get("actions_enabled", True)
        and number is not None
        and _can_check(show.get("source"))
        else None,
    }


def _now():
    from django.utils import timezone

    return timezone.now()


def build_detail_season(request, show_context, season_number) -> dict | None:
    """One season of a show page's episode list (the season's own fragment)."""
    from app.season_details_views import build_season_details_context

    show = show_context["media"]
    media_type = show_context["media_type"]
    context = build_season_details_context(
        request,
        show.get("source"),
        show.get("media_id"),
        app_tags.slug(show.get("title") or ""),
        season_number,
        MediaTypes.ANIME.value if media_type == MediaTypes.ANIME.value else None,
    )
    if not isinstance(context, dict):
        return None
    season = context["media"]
    user = request.user
    next_target = app_tags.ct_detail_next_episode(
        show, show_context.get("current_instance")
    )
    next_number = (
        next_target["episode_number"]
        if next_target and next_target["season_number"] == season_number
        else None
    )
    progress = None
    if not context.get("public_view"):
        numbers = app_tags.ct_series_progress(season, context.get("current_instance"))
        if numbers:
            progress = {
                "watched": numbers["watched"],
                "total": numbers["total"],
                "percent": numbers["percent"],
                "dashes": [
                    {"label": _text(dash["label"]), "percent": dash["percent"]}
                    for dash in numbers["dashes"]
                ],
            }
    load_more = context.get("episode_load_more")
    details = season.get("details") or {}
    year = app_tags.release_year(details)
    cast_row = context.get("cast_row") or {}
    character_images = (
        app_tags.ct_character_images({"request": request}, season) if cast_row.get("total") else {}
    )
    info = {
        "title": _text(season.get("season_title")) or "Season",
        "poster": _image(season.get("image"), "w185")
        if season.get("image") and season.get("image") != settings.IMG_NONE
        else None,
        "year": _text(year) or None,
        "episodes": details.get("episodes") or None,
        "runtime": _text(details.get("runtime")) or None,
        "score": _text(season.get("score")) if season.get("score") else None,
        "synopsis": strip_tags(_text(season.get("synopsis"))).strip(),
        "cast": [
            _person(person, show, character_images)
            for person in cast_row.get("items") or []
        ]
        if cast_row.get("total")
        else [],
    }
    return {
        "number": season_number,
        "info": info,
        "progress": progress,
        "episodes": [
            _episode(episode, show, season_number, user, next_number, media_type)
            for episode in season.get("episodes") or []
            if isinstance(episode, dict)
        ],
        "load_more": {
            "querystring": _text(load_more.get("querystring")),
            "label": _text(load_more.get("label")),
        }
        if load_more
        else None,
    }


def _issues(media, user) -> list[dict]:
    """Return a comic volume's issues (issue_row.html) from the page's episodes."""
    issues = []
    for episode in media.get("episodes") or []:
        if not isinstance(episode, dict):
            continue
        number = _text(episode.get("issue_number"))
        title = _text(episode.get("title"))
        try:
            url = reverse(
                "media_details",
                kwargs={
                    "source": episode.get("source"),
                    "media_type": episode.get("media_type"),
                    "media_id": episode.get("media_id"),
                    "title": app_tags.slug(title or number),
                },
            )
        except NoReverseMatch:
            url = None
        image = episode.get("image")
        issues.append(
            {
                "number": number,
                "title": title,
                "image": _image(image, "w342")
                if image and image != settings.IMG_NONE
                else None,
                "cover_date": _text(episode.get("cover_date")),
                "read": bool(episode.get("history")),
                "url": url,
                "media_type": MediaTypes.COMIC_ISSUE.value,
                "source": _text(episode.get("source")),
                "media_id": _text(episode.get("media_id")),
            }
        )
    return issues


def _flat_episodes(context, user) -> list[dict]:
    """Return a flat MAL anime's mapped episodes, read-only (this page of them).

    Each row links to the mapped provider's anime episode page (its own
    media_id, source and season, as ct/detail_secondary.html does) and has no
    check: the ensure endpoint takes no MAL show.
    """
    media = context["media"]
    episodes = media.get("episodes")
    if media.get("source") != Sources.MAL.value or not isinstance(episodes, list):
        return []
    rows = []
    for episode in episodes:
        if not isinstance(episode, dict) or not episode.get("source"):
            continue
        row_show = {
            "source": episode["source"],
            "media_id": episode.get("media_id"),
            "title": media.get("title"),
        }
        rows.append(
            _episode(
                episode,
                row_show,
                episode.get("season_number") or 0,
                user,
                None,
                MediaTypes.ANIME.value,
                read_only=True,
            )
        )
    return rows


def _flat_note(context) -> str:
    """Return "This entry maps to TMDB Season 2 (episodes 1-12)." for a mapped entry."""
    target = context.get("grouped_preview_target")
    display = context.get("display_provider")
    if not isinstance(target, dict) or display == context.get("identity_provider"):
        return ""
    note = f"This entry maps to {_text(display).upper()} "
    note += _text(target.get("season_title")) or "season"
    start, end = target.get("episode_start"), target.get("episode_end")
    if start and end:
        note += f" (episodes {start}-{end})"
    elif start:
        note += f" (starting at episode {start})"
    return note + "."


def _issues_more(load_more) -> dict | None:
    """Return the next page of issues: its number and the "Show" label."""
    if not load_more:
        return None
    try:
        page = int(parse_qs(_text(load_more.get("querystring"))).get("episode_page", [""])[0])
    except ValueError:
        return None
    return {"page": page, "label": _text(load_more.get("label"))}


def _game_lengths(context) -> dict:
    """Return a game's Time to Beat (game_lengths_section.html), no icon keys.

    Every game gets it, as on the page: without data or a fetch it says the
    figures are not available yet.
    """
    lengths = context.get("game_lengths") or {}
    pending = bool(context.get("game_lengths_pending"))
    return {
        "available": bool(lengths.get("available")),
        "pending": pending,
        "source_label": _text(lengths.get("source_label")),
        "source_url": lengths.get("source_url") or None,
        "cards": [
            {
                "label": _text(card.get("label")),
                "value": _text(card.get("value")),
                "count": card.get("count") or 0,
            }
            for card in lengths.get("cards") or []
        ],
    }


def _authors(context) -> list[dict]:
    """Return the linked authors (detail_secondary_content.html)."""
    authors = []
    for author in context.get("authors_linked") or []:
        try:
            url = reverse(
                "person_detail",
                kwargs={
                    "source": author["source"],
                    "person_id": author["person_id"],
                    "name": app_tags.slug(author["name"]),
                },
            )
        except (NoReverseMatch, KeyError):
            continue
        authors.append({"name": _text(author["name"]), "url": url})
    return authors


def _studios(context) -> list[dict]:
    studios = []
    for studio in (context.get("studios_linked") or [])[:12]:
        name = studio.get("name") if isinstance(studio, dict) else getattr(studio, "name", "")
        studios.append(
            {
                "name": _text(name) or "Unknown Studio",
                "url": app_tags.studio_url(studio) or None,
            }
        )
    return studios


def _genres(media, media_type) -> list[dict]:
    try:
        base = reverse("medialist", kwargs={"media_type": media_type})
    except NoReverseMatch:
        return []
    return [
        {"name": _text(genre), "url": f"{base}?genre={quote(_text(genre))}"}
        for genre in media.get("genres") or []
    ]


def _selected_season(request, context) -> int | None:
    covers = app_tags.ct_season_covers(
        context["media"],
        request.GET.get("season")
        or (
            app_tags.ct_detail_next_episode(
                context["media"], context.get("current_instance")
            )
            or {}
        ).get("season_number"),
    )
    for cover in covers:
        if cover["current"]:
            return cover["number"]
    return None


def build_detail_sections(request, context) -> dict:
    """Return the sections below the hero: the page's secondary phase."""
    media = context["media"]
    user = request.user
    media_type = context["media_type"]
    seasons = []
    season = None
    if media_type in _SERIES_TYPES and (media.get("related") or {}).get("seasons"):
        selected = _selected_season(request, context)
        seasons = [
            {
                "number": cover["number"],
                "label": _text(cover["label"]),
                "short": _text(cover["short"]),
                "image": _image(cover["image"], "w185") if cover["image"] else None,
                "current": cover["current"],
            }
            for cover in app_tags.ct_season_covers(media, selected)
        ]
        if selected is not None:
            season = build_detail_season(request, context, selected)
    related = []
    for name, items in (media.get("related") or {}).items():
        if name in ("seasons", "recommendations") or not items:
            continue
        related.append(
            {
                "name": name.replace("_", " ").title(),
                "cards": [_card(entry, user) for entry in items],
            }
        )
    cast_row = context.get("cast_row") or {}
    crew_row = context.get("crew_row") or {}
    # TVDB's character pictures for the Characters tab (a title's first read
    # takes 0.5 to 1.9 s, then a week's cache), as the page reads them.
    character_images = (
        app_tags.ct_character_images({"request": request}, media) if cast_row.get("total") else {}
    )
    recommendations = (context.get("recommendations_row") or {}).get("items") or []
    public = bool(context.get("public_view"))
    l1 = media_type in L1_TYPES
    authors = _authors(context) if l1 else []
    studios = _studios(context) if l1 else []
    flat_episodes = (
        _flat_episodes(context, user)
        if media_type == MediaTypes.ANIME.value and not seasons
        else []
    )
    return {
        "backdrop": _backdrop(media, allow_network=True),
        **_fanart(media, allow_network=True),
        "watch_on": _watch_on(context.get("watch_on")),
        "sections": _sections(user, media_type),
        "seasons": seasons,
        "season": season,
        "plays": _plays(context, user)
        if media_type == MediaTypes.MOVIE.value and not public
        else [],
        "history_url": f"{reverse('history')}?media_type={media_type}"
        f"&media_id={media.get('media_id')}&source={media.get('source')}",
        "related": related,
        "cast": [
            _person(person, media, character_images) for person in cast_row.get("items") or []
        ]
        if cast_row.get("total")
        else [],
        "crew": [_person(person, media) for person in crew_row.get("items") or []]
        if crew_row.get("total")
        else [],
        "cast_view_all_url": cast_row.get("view_all_url") or None,
        "recommendations": [_card(entry, user) for entry in recommendations]
        if (media.get("related") or {}).get("recommendations")
        else [],
        "info": _info(context, user, authors=authors, studios=studios),
        "issues": _issues(media, user) if media_type == MediaTypes.COMIC.value else [],
        "issues_more": _issues_more(context.get("episode_load_more"))
        if media_type == MediaTypes.COMIC.value
        else None,
        "game_lengths": _game_lengths(context)
        if media_type == MediaTypes.GAME.value
        else None,
        "flat_episodes": flat_episodes,
        "flat_more": _issues_more(context.get("episode_load_more"))
        if flat_episodes
        else None,
        "flat_note": _flat_note(context) if flat_episodes else "",
        "authors": authors,
        "studios": studios,
        "genres": _genres(media, media_type) if l1 else [],
    }


def build_detail_screen(request, media_type, source, media_id, part) -> dict | object:
    """Return the detail page's ``part`` for the web, or the page's redirect."""
    from django.http import HttpResponse

    from app.media_details_views import build_media_details_context

    if part == "trailers":
        # The page's ?fragment=trailers: no page context, only TMDB's videos.
        from app import carousel as carousel_media
        from app.providers import services

        try:
            trailers = carousel_media.resolve_trailers(media_type, source, media_id)
        except services.ProviderAPIError:
            trailers = []
        return {
            "trailers": [
                {
                    "key": _text(trailer.get("key")),
                    "name": _text(trailer.get("name") or trailer.get("type")),
                    "type": _text(trailer.get("type")),
                    "season": trailer.get("season"),
                }
                for trailer in trailers
                if trailer.get("key")
            ]
        }

    built = build_media_details_context(
        request,
        source,
        media_type,
        media_id,
        "",
        # A season reads the show from the warm caches the sections left.
        secondary=part == "secondary",
    )
    if isinstance(built, HttpResponse):
        return built
    context, _template = built
    if part == "shell":
        return build_detail_shell(request, context)
    if part == "season":
        try:
            number = int(request.GET.get("season", ""))
        except ValueError:
            number = _selected_season(request, context)
        return (
            build_detail_season(request, context, number)
            if number is not None
            else None
        )
    return build_detail_sections(request, context)


# --- serializers -------------------------------------------------------------


class DetailScoreSerializer(serializers.Serializer):
    """The detail page's score."""

    key = serializers.CharField(help_text="provider, trakt, imdb or mal.")
    label = serializers.CharField()
    short = serializers.CharField(help_text="The chip's badge: TMDB, Trakt, IMDb, MAL.")
    rating = serializers.CharField()
    count = serializers.IntegerField(allow_null=True)


class DetailWatchChipSerializer(serializers.Serializer):
    """The detail page's watch chip."""

    name = serializers.CharField()
    image = serializers.CharField()
    offer = serializers.CharField()


class DetailWatchOnSerializer(serializers.Serializer):
    """The detail page's watch on."""

    subscription = DetailWatchChipSerializer(many=True)
    rent_buy = DetailWatchChipSerializer(many=True)
    link = serializers.CharField(allow_null=True)


class DetailMetaSerializer(serializers.Serializer):
    """The detail page's meta."""

    type_label = serializers.CharField()
    genres = serializers.ListField(child=serializers.CharField())
    year = serializers.CharField(allow_null=True)
    runtime = serializers.CharField(allow_null=True)
    certification = serializers.CharField(allow_null=True)
    seasons = serializers.IntegerField(allow_null=True)
    percent = serializers.IntegerField(allow_null=True)
    progress = serializers.CharField(
        allow_null=True,
        help_text="Books, manga, games, comics: your progress line (Progress: 120/300).",
    )
    series = serializers.CharField(
        allow_null=True, help_text="Books: the series and the book's place in it."
    )


class DetailActionSerializer(serializers.Serializer):
    """The detail page's action."""

    kind = serializers.CharField(
        help_text=(
            "mark: log a movie play; watched: the movie is watched; episode: "
            "mark `episode` watched (null: the first unwatched aired episode "
            "of the season on screen); completed: a completed show."
        )
    )
    episode = HomeCheckTargetSerializer(allow_null=True)


class DetailLinkSerializer(serializers.Serializer):
    """A link chip: a provider page or an external database."""

    label = serializers.CharField()
    url = serializers.CharField()
    logo = serializers.CharField(allow_null=True)
    fallback = serializers.CharField(allow_blank=True, help_text="Badge text without a logo.")


class DetailLinkSectionSerializer(serializers.Serializer):
    """A group of links in the links popover."""

    title = serializers.CharField()
    links = DetailLinkSerializer(many=True)


class DetailShellSerializer(serializers.Serializer):
    """The detail page's shell."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField()
    page_url = serializers.CharField(
        help_text="The Django page, for every action not here yet."
    )
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    backdrop = serializers.CharField(allow_null=True)
    fanart_poster = serializers.CharField(
        allow_null=True, help_text="fanart.tv's poster, shown in place of `poster`."
    )
    logo = serializers.CharField(allow_null=True, help_text="fanart.tv's title logo.")
    links = DetailLinkSectionSerializer(many=True)
    meta = DetailMetaSerializer()
    scores = DetailScoreSerializer(many=True)
    my_score = serializers.FloatField(allow_null=True)
    status = serializers.CharField(allow_null=True)
    action = DetailActionSerializer(allow_null=True)
    synopsis = serializers.CharField(allow_blank=True)
    watch_on = DetailWatchOnSerializer(allow_null=True)
    track_time = serializers.BooleanField()


class DetailSeasonCoverSerializer(serializers.Serializer):
    """The detail page's season cover."""

    number = serializers.IntegerField()
    label = serializers.CharField()
    short = serializers.CharField()
    image = serializers.CharField(allow_null=True)
    current = serializers.BooleanField()


class DetailDashSerializer(serializers.Serializer):
    """One episode's dash in a season's progress strip."""

    label = serializers.CharField()
    percent = serializers.IntegerField()


class DetailProgressSerializer(serializers.Serializer):
    """The detail page's progress."""

    watched = serializers.IntegerField()
    total = serializers.IntegerField(allow_null=True)
    percent = serializers.IntegerField()
    dashes = DetailDashSerializer(many=True)


class DetailEpisodeSerializer(serializers.Serializer):
    """The detail page's episode."""

    episode_number = serializers.IntegerField(allow_null=True)
    display_number = serializers.CharField(allow_null=True)
    title = serializers.CharField(allow_blank=True)
    still = serializers.CharField()
    still_srcset = serializers.CharField(allow_blank=True)
    placeholder = serializers.BooleanField()
    air_date = serializers.CharField()
    aired = serializers.BooleanField()
    runtime = serializers.CharField(allow_null=True)
    overview = serializers.CharField(allow_blank=True)
    blurred = serializers.BooleanField()
    watched = serializers.BooleanField()
    history = serializers.CharField(allow_blank=True)
    is_next = serializers.BooleanField()
    url = serializers.CharField(allow_null=True)
    check = HomeCheckTargetSerializer(allow_null=True)


class DetailLoadMoreSerializer(serializers.Serializer):
    """The detail page's load more."""

    querystring = serializers.CharField()
    label = serializers.CharField()


class DetailPersonSerializer(serializers.Serializer):
    """A cast or crew card; crew cards carry the job as `role`."""

    name = serializers.CharField()
    role = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_null=True)
    character_image = serializers.CharField(
        allow_null=True, help_text="TVDB's picture of the character, for the Characters tab."
    )
    url = serializers.CharField(allow_null=True)


class DetailSeasonInfoSerializer(serializers.Serializer):
    """A season's info dialog (the season fragment's #ct-season-info)."""

    title = serializers.CharField()
    poster = serializers.CharField(allow_null=True)
    year = serializers.CharField(allow_null=True)
    episodes = serializers.IntegerField(allow_null=True)
    runtime = serializers.CharField(allow_null=True)
    score = serializers.CharField(allow_null=True, help_text="TMDB's season score.")
    synopsis = serializers.CharField(allow_blank=True)
    cast = DetailPersonSerializer(many=True)


class DetailSeasonSerializer(serializers.Serializer):
    """The detail page's season."""

    number = serializers.IntegerField()
    info = DetailSeasonInfoSerializer()
    progress = DetailProgressSerializer(allow_null=True)
    episodes = DetailEpisodeSerializer(many=True)
    load_more = DetailLoadMoreSerializer(allow_null=True)


class DetailPlaySerializer(serializers.Serializer):
    """The detail page's play."""

    status = serializers.CharField()
    label = serializers.CharField()
    when = serializers.CharField()
    score = serializers.CharField(allow_null=True)


class DetailCardSerializer(serializers.Serializer):
    """The detail page's card."""

    media_type = serializers.CharField(allow_null=True)
    title = serializers.CharField()
    url = serializers.CharField()
    poster = serializers.CharField()
    poster_srcset = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    status = serializers.CharField(
        allow_null=True, help_text="The user's status, for the chip."
    )


class DetailRelatedSerializer(serializers.Serializer):
    """The detail page's related."""

    name = serializers.CharField()
    cards = DetailCardSerializer(many=True)


class DetailInfoSerializer(serializers.Serializer):
    """The detail page's info."""

    label = serializers.CharField()
    value = serializers.CharField(allow_blank=True)


class DetailIssueSerializer(serializers.Serializer):
    """A comic volume's issue."""

    number = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_null=True)
    cover_date = serializers.CharField(allow_blank=True)
    read = serializers.BooleanField()
    url = serializers.CharField(allow_null=True)
    media_type = serializers.CharField(help_text="comicissue, for the track dialog.")
    source = serializers.CharField()
    media_id = serializers.CharField()


class DetailIssuesMoreSerializer(serializers.Serializer):
    """The next page of a volume's issues."""

    page = serializers.IntegerField(help_text="Pass it as `episode_page`.")
    label = serializers.CharField(allow_blank=True)


class DetailGameLengthCardSerializer(serializers.Serializer):
    """One Time to Beat figure."""

    label = serializers.CharField()
    value = serializers.CharField()
    count = serializers.IntegerField(help_text="The submissions behind it.")


class DetailGameLengthsSerializer(serializers.Serializer):
    """A game's Time to Beat."""

    available = serializers.BooleanField()
    pending = serializers.BooleanField(
        help_text="The figures are being fetched in the background."
    )
    source_label = serializers.CharField(allow_blank=True)
    source_url = serializers.CharField(allow_null=True)
    cards = DetailGameLengthCardSerializer(many=True)


class DetailNamedLinkSerializer(serializers.Serializer):
    """An author, studio or genre, with the Django page it opens."""

    name = serializers.CharField()
    url = serializers.CharField(allow_null=True)


class DetailSectionsSerializer(serializers.Serializer):
    """The detail page's sections."""

    backdrop = serializers.CharField(allow_null=True)
    watch_on = DetailWatchOnSerializer(allow_null=True)
    sections = serializers.ListField(
        child=serializers.CharField(),
        help_text="The visible sections, in the user's detail layout order.",
    )
    seasons = DetailSeasonCoverSerializer(many=True)
    season = DetailSeasonSerializer(allow_null=True)
    plays = DetailPlaySerializer(many=True)
    history_url = serializers.CharField()
    related = DetailRelatedSerializer(many=True)
    cast = DetailPersonSerializer(many=True)
    crew = DetailPersonSerializer(many=True)
    cast_view_all_url = serializers.CharField(allow_null=True)
    recommendations = DetailCardSerializer(many=True)
    info = DetailInfoSerializer(many=True)
    issues = DetailIssueSerializer(
        many=True, help_text="Comics: this page of the volume's issues."
    )
    issues_more = DetailIssuesMoreSerializer(allow_null=True)
    flat_episodes = DetailEpisodeSerializer(
        many=True,
        help_text="Flat MAL anime: this page of the mapped episodes, read-only.",
    )
    flat_more = DetailIssuesMoreSerializer(allow_null=True)
    flat_note = serializers.CharField(
        allow_blank=True, help_text="Where the flat entry maps (TMDB or TVDB)."
    )
    game_lengths = DetailGameLengthsSerializer(allow_null=True)
    authors = DetailNamedLinkSerializer(many=True)
    studios = DetailNamedLinkSerializer(many=True)
    genres = DetailNamedLinkSerializer(many=True)
    fanart_poster = serializers.CharField(allow_null=True)
    logo = serializers.CharField(allow_null=True)


class DetailTrailerSerializer(serializers.Serializer):
    """A YouTube trailer or teaser (ct/trailers.html)."""

    key = serializers.CharField(help_text="The YouTube video id.")
    name = serializers.CharField()
    type = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)


class DetailTrailersSerializer(serializers.Serializer):
    """A movie's or show's trailers: its own first, then each season's."""

    trailers = DetailTrailerSerializer(many=True)
