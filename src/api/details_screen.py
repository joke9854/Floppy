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

from django.conf import settings
from django.urls import NoReverseMatch, reverse
from django.utils.html import strip_tags
from rest_framework import serializers

from app.models import MediaTypes, Status
from app.templatetags import app_tags
from users.appearance import resolved_detail_layouts
from users.templatetags import user_tags

from .home_screen import HomeCheckTargetSerializer

DETAIL_SCREEN_TYPES = (MediaTypes.MOVIE.value, MediaTypes.TV.value)
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
# Information grid keys the template leaves out.
_INFO_SKIPPED = {"themes", "format", "last_air_date", "seasons", "episodes"}


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
                    "rating": _text(score.get("rating")),
                    "count": score.get("rating_count"),
                }
            )
    return scores


def _check_target(target) -> dict | None:
    if not target:
        return None
    return {
        "source": target["source"],
        "media_id": str(target["media_id"]),
        "season_number": target["season_number"],
        "episode_number": target["episode_number"],
        "library_media_type": target.get("library_media_type"),
    }


def _action(context) -> dict | None:
    """Return the hero's filled button (ct/detail_hero.html)."""
    if context.get("public_view"):
        return None
    media_type = context["media_type"]
    current = context.get("current_instance")
    status = getattr(current, "status", None)
    if media_type == MediaTypes.MOVIE.value:
        if status == Status.COMPLETED.value:
            return {"kind": "watched", "episode": None}
        if current is None or status == Status.PLANNING.value:
            return {"kind": "mark", "episode": None}
        return None
    target = app_tags.ct_detail_next_episode(context["media"], current)
    if target:
        return {"kind": "episode", "episode": _check_target(target)}
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
    if media_type == MediaTypes.TV.value and not context.get("public_view"):
        progress = app_tags.ct_series_progress(media, context.get("current_instance"))
        percent = (progress or {}).get("percent") or None
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
        "seasons": details.get("seasons")
        if media_type == MediaTypes.TV.value
        else None,
        "percent": percent,
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
    year = app_tags._ct_value(item, "year") or app_tags.release_year(item) or None
    return {
        "media_type": app_tags._ct_value(item, "media_type"),
        "title": _text(app_tags.display_title(item, user)),
        "url": app_tags.media_url(item),
        "poster": _image(image, "w342"),
        "poster_srcset": app_tags.tmdb_srcset(image) or "",
        "subtitle": _text(year),
    }


def _person(person, media) -> dict:
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
    return {
        "name": _text(person.get("name")) or "Unknown",
        "role": _text(person.get("role")),
        "image": app_tags.image_url(image)
        if image and image != settings.IMG_NONE
        else None,
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


def _info(context, user) -> list[dict]:
    """Return the Information grid (the page's labels and date formats)."""
    media = context["media"]
    details = media.get("details") or {}
    rows = []
    for key, value in details.items():
        if key in _INFO_SKIPPED or not value:
            continue
        if key == "first_air_date":
            label = "Aired"
            text = _text(user_tags.user_date_format(value, user))
            last = details.get("last_air_date")
            if last and last != value:
                text += f" – {user_tags.user_date_format(last, user)}"  # noqa: RUF001  # the page's en dash
        else:
            if key == "studios" and context["media_type"] != MediaTypes.MOVIE.value:
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
    return [key for key, zone in _SECTIONS if key in layouts.get(zone, [])]


def _episode(episode, show, season_number, user, next_number) -> dict:
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
                "episode_details",
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
            "library_media_type": getattr(item, "library_media_type", None),
        }
        if episode.get("actions_enabled", True) and number is not None
        else None,
    }


def _now():
    from django.utils import timezone

    return timezone.now()


def build_detail_season(request, show_context, season_number) -> dict | None:
    """One season of a show page's episode list (the season's own fragment)."""
    from app.season_details_views import build_season_details_context

    show = show_context["media"]
    context = build_season_details_context(
        request,
        show.get("source"),
        show.get("media_id"),
        app_tags.slug(show.get("title") or ""),
        season_number,
        None,
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
            }
    load_more = context.get("episode_load_more")
    return {
        "number": season_number,
        "progress": progress,
        "episodes": [
            _episode(episode, show, season_number, user, next_number)
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
    if media_type == MediaTypes.TV.value and (media.get("related") or {}).get(
        "seasons"
    ):
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
    recommendations = (context.get("recommendations_row") or {}).get("items") or []
    public = bool(context.get("public_view"))
    return {
        "backdrop": _backdrop(media, allow_network=True),
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
        "cast": [_person(person, media) for person in cast_row.get("items") or []]
        if cast_row.get("total")
        else [],
        "cast_view_all_url": cast_row.get("view_all_url") or None,
        "recommendations": [_card(entry, user) for entry in recommendations]
        if (media.get("related") or {}).get("recommendations")
        else [],
        "info": _info(context, user),
    }


def build_detail_screen(request, media_type, source, media_id, part) -> dict | object:
    """Return the detail page's ``part`` for the web, or the page's redirect."""
    from django.http import HttpResponse

    from app.media_details_views import build_media_details_context

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


class DetailProgressSerializer(serializers.Serializer):
    """The detail page's progress."""

    watched = serializers.IntegerField()
    total = serializers.IntegerField(allow_null=True)
    percent = serializers.IntegerField()


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


class DetailSeasonSerializer(serializers.Serializer):
    """The detail page's season."""

    number = serializers.IntegerField()
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


class DetailRelatedSerializer(serializers.Serializer):
    """The detail page's related."""

    name = serializers.CharField()
    cards = DetailCardSerializer(many=True)


class DetailPersonSerializer(serializers.Serializer):
    """The detail page's person."""

    name = serializers.CharField()
    role = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_null=True)
    url = serializers.CharField(allow_null=True)


class DetailInfoSerializer(serializers.Serializer):
    """The detail page's info."""

    label = serializers.CharField()
    value = serializers.CharField(allow_blank=True)


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
    cast_view_all_url = serializers.CharField(allow_null=True)
    recommendations = DetailCardSerializer(many=True)
    info = DetailInfoSerializer(many=True)
