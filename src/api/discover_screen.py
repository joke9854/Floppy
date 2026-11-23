"""The web Discover screen (v2 P4-G).

`GET /api/v1/discover/screen/` reads the Django Discover page's own context
(`build_discover_context`): the type tabs, the hero, the rows and the Hidden
view. Each card carries the fields the page's quick actions post to
`discover_action` (Add to Planning, Hide from Discover), written as the
page's card and hero write them (media_card.html, ct/discover_hero.html).
`/api/v1/discover/rows/` stays the CineTrack app's contract.
"""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse
from django.utils import dateformat, timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import serializers

from app.templatetags import app_tags

SQUARE_TYPES = {"music", "podcast"}
CONTINUE_ROWS = {
    "continue_all",
    "continue_up_next",
    "next_episode",
    "continue",
    "clear_out_next",
}


def _type_label(media_type) -> str:
    try:
        return str(app_tags.media_type_readable(media_type))
    except (ValueError, KeyError):
        return str(media_type or "")


def _year(value) -> str:
    return str(value or "")[:4]


def _action(candidate, *, title: str, row_key: str, active: str, show_more: bool) -> dict:
    """Return the fields the page posts to discover_action for this candidate.

    ``image`` stays the stored value (not the image-cache URL): a Hide seeds a
    new Item from it.
    """
    return {
        "candidate_media_type": str(candidate.media_type or ""),
        "identity_media_type": str(getattr(candidate, "identity_media_type", "") or ""),
        "library_media_type": str(getattr(candidate, "library_media_type", "") or ""),
        "source": str(candidate.source or ""),
        "media_id": str(candidate.media_id or ""),
        "season_number": str(getattr(candidate, "season_number", "") or ""),
        "active_media_type": active or "all",
        "show_more": "1" if show_more else "0",
        "row_key": row_key,
        "title": title,
        "image": str(candidate.image or settings.IMG_NONE),
        "release_date": str(candidate.release_date or ""),
    }


def _card(candidate, user, *, row_key: str, active: str, show_more: bool) -> dict:
    title = str(app_tags.display_title(candidate, user) or candidate.title or "")
    image = candidate.image or settings.IMG_NONE
    sub = _type_label(candidate.media_type)
    if candidate.release_date:
        sub = f"{sub} · {_year(candidate.release_date)}"
    return {
        "key": f"{candidate.media_type}:{candidate.source}:{candidate.media_id}",
        "media_type": str(candidate.media_type or ""),
        "title": title,
        "href": str(app_tags.media_url(candidate) or ""),
        "poster": str(app_tags.image_url(app_tags.tmdb_size(image, "w342")) or ""),
        "poster_srcset": str(app_tags.tmdb_srcset(image) or ""),
        "sub": sub,
        "lists_url": str(app_tags.media_view_url("lists_modal", candidate) or ""),
        "action": _action(
            candidate,
            title=title,
            row_key=row_key,
            active=active,
            show_more=show_more,
        ),
    }


def _row(row, user, *, active: str, show_more: bool) -> dict:
    items = list(row.items or [])
    if row.key in CONTINUE_ROWS:
        empty = _(
            "Nothing to continue yet. Track something as in progress and it will appear here.",
        )
    else:
        empty = _("No items matched this row right now.")
    return {
        "key": str(row.key),
        "title": str(row.title),
        "square": bool(items) and items[0].media_type in SQUARE_TYPES,
        "empty_message": empty,
        "cards": [
            _card(candidate, user, row_key=row.key, active=active, show_more=show_more)
            for candidate in items
        ],
    }


def _slide(slide, user, *, active: str, show_more: bool) -> dict:
    candidate = slide["candidate"]
    title = str(app_tags.display_title(candidate, user) or candidate.title or "")
    meta = [_type_label(candidate.media_type)]
    if candidate.genres:
        meta.append(str(candidate.genres[0]))
    if candidate.release_date:
        meta.append(_year(candidate.release_date))
    backdrop = slide.get("backdrop") or ""
    logo = slide.get("logo") or ""
    return {
        "key": f"{candidate.media_type}:{candidate.source}:{candidate.media_id}",
        "title": title,
        "href": str(app_tags.media_url(candidate) or ""),
        "meta": " · ".join(meta),
        "backdrop": str(app_tags.image_url(app_tags.tmdb_size(backdrop, "w780")) or ""),
        "backdrop_srcset": str(app_tags.tmdb_srcset(backdrop, "w780,w1280") or ""),
        "logo": str(app_tags.image_url(logo) or "") if logo else "",
        # The hero posts the candidate's own title and no row (ct/discover_hero.html).
        "action": _action(
            candidate,
            title=str(candidate.title or ""),
            row_key="",
            active=active,
            show_more=show_more,
        ),
    }


def _hidden(entry) -> dict:
    item = entry.item
    meta = [_type_label(item.library_media_type or item.media_type)]
    if item.release_datetime:
        meta.append(str(item.release_datetime.year))
    hidden_on = dateformat.format(timezone.localtime(entry.updated_at), "j M")
    meta.append(_("Hidden %(date)s") % {"date": hidden_on})
    image = item.image if item.image and item.image != settings.IMG_NONE else ""
    return {
        "item_id": item.id,
        "title": str(item.title or ""),
        "poster": str(app_tags.image_url(app_tags.tmdb_size(image, "w154")) or "") if image else "",
        "meta": " · ".join(meta),
    }


def build_discover_screen(request) -> dict:
    """Return the Discover screen for the web from the page's context."""
    from app.discover_views import build_discover_context

    context = build_discover_context(request)
    user = request.user
    active = context["selected_media_type"]
    show_more = bool(context["show_more"])
    options = [
        {
            "value": option["value"],
            "label": _("All") if option["value"] == "all" else _(str(option["label"])),
            "primary": bool(option.get("primary")),
        }
        for option in context["discover_media_options"]
        if option["value"] != "hidden"
    ]
    rows = list(context.get("rows") or [])
    hero = []
    if rows:
        hero = [
            _slide(slide, user, active=active, show_more=show_more)
            for slide in app_tags.ct_discover_hero(rows)
        ]
    hidden_count = int(context.get("hidden_discover_count") or 0)
    return {
        "media_type": active,
        "show_more": show_more,
        "loading": bool(context.get("discover_loading")),
        "options": options,
        "hidden_count": hidden_count,
        "hidden_summary": ngettext(
            "%(count)s item · it stays out of recommendations until you unhide it",
            "%(count)s items · they stay out of recommendations until you unhide them",
            hidden_count,
        )
        % {"count": hidden_count},
        "hero": hero,
        "rows": [_row(row, user, active=active, show_more=show_more) for row in rows],
        "hidden": [_hidden(entry) for entry in context.get("hidden_discover_entries") or []],
        "action_url": reverse("discover_action"),
        "refresh_url": reverse("refresh_discover"),
        "hide_url": reverse("discover_toggle_hidden"),
        "status_url": reverse("cache_status"),
    }


class DiscoverScreenOptionSerializer(serializers.Serializer):
    """A Discover type tab (Movies, Shows…); `primary` ones sit in the bar."""

    value = serializers.CharField()
    label = serializers.CharField()
    primary = serializers.BooleanField()


class DiscoverScreenActionSerializer(serializers.Serializer):
    """The form fields a quick action posts to `/discover/action` (with `action`)."""

    candidate_media_type = serializers.CharField()
    identity_media_type = serializers.CharField(allow_blank=True)
    library_media_type = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    media_id = serializers.CharField()
    season_number = serializers.CharField(allow_blank=True)
    active_media_type = serializers.CharField()
    show_more = serializers.CharField()
    row_key = serializers.CharField(allow_blank=True)
    title = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_blank=True)
    release_date = serializers.CharField(allow_blank=True)


class DiscoverScreenCardSerializer(serializers.Serializer):
    """A row's card: poster, title, "Type · Year"."""

    key = serializers.CharField()
    media_type = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    poster = serializers.CharField(allow_blank=True)
    poster_srcset = serializers.CharField(allow_blank=True)
    sub = serializers.CharField(allow_blank=True)
    lists_url = serializers.CharField(
        allow_blank=True,
        help_text="The card's Lists dialog (`/lists_modal/...`, JSON with Accept: application/json).",
    )
    action = DiscoverScreenActionSerializer()


class DiscoverScreenRowSerializer(serializers.Serializer):
    """A Discover row; `square` for music and podcasts."""

    key = serializers.CharField()
    title = serializers.CharField()
    square = serializers.BooleanField()
    empty_message = serializers.CharField()
    cards = DiscoverScreenCardSerializer(many=True)


class DiscoverScreenSlideSerializer(serializers.Serializer):
    """A hero slide: one pick per row with a backdrop."""

    key = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    meta = serializers.CharField(allow_blank=True)
    backdrop = serializers.CharField(allow_blank=True)
    backdrop_srcset = serializers.CharField(allow_blank=True)
    logo = serializers.CharField(allow_blank=True)
    action = DiscoverScreenActionSerializer()


class DiscoverScreenHiddenSerializer(serializers.Serializer):
    """An item hidden from Discover (Unhide posts `item_id` to `hide_url`)."""

    item_id = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    poster = serializers.CharField(allow_blank=True)
    meta = serializers.CharField(allow_blank=True)


class DiscoverScreenSerializer(serializers.Serializer):
    """The Discover page for the web app."""

    media_type = serializers.CharField()
    show_more = serializers.BooleanField()
    loading = serializers.BooleanField()
    options = DiscoverScreenOptionSerializer(many=True)
    hidden_count = serializers.IntegerField()
    hidden_summary = serializers.CharField()
    hero = DiscoverScreenSlideSerializer(many=True)
    rows = DiscoverScreenRowSerializer(many=True)
    hidden = DiscoverScreenHiddenSerializer(many=True)
    action_url = serializers.CharField()
    refresh_url = serializers.CharField()
    hide_url = serializers.CharField()
    status_url = serializers.CharField()
