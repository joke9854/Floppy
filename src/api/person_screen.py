"""The web person page's data (v2 P4-C3): the Django person page, as JSON.

`app.people_views.build_person_context` is the page's own builder, so this
shows the same person, numbers, Known For and filmography as /person/...;
values follow the CineTrack template (`ct/person_page.html`).
"""

from __future__ import annotations

from django.conf import settings
from django.utils.html import strip_tags
from rest_framework import serializers

from app.templatetags import app_tags
from users.templatetags import user_tags


def _text(value) -> str:
    return "" if value is None else str(value)


def _poster(entry, size: str) -> str:
    return app_tags.image_url(app_tags.tmdb_size(entry.get("image") or settings.IMG_NONE, size))


def _card(entry, *, watched: bool) -> dict:
    """Return a credit poster card (ct/person_credit_card.html)."""
    return {
        "title": _text(entry.get("title")),
        "url": app_tags.media_url(entry),
        "poster": _poster(entry, "w342"),
        "year": _text(entry.get("year")),
        "media_type": _text(entry.get("media_type")),
        "watched": watched,
    }


def _credit(entry) -> dict:
    """Return a filmography row (the list in ct/person_page.html)."""
    departments = [str(name) for name in entry.get("all_departments") or []]
    return {
        "title": _text(entry.get("title")),
        "url": app_tags.media_url(entry),
        "thumb": _poster(entry, "w92"),
        "year": _text(entry.get("year")),
        "role": _text(entry.get("role")),
        "media_type": _text(entry.get("media_type")),
        "type_label": _text(app_tags.media_type_readable(entry.get("media_type"))),
        "departments": departments if len(departments) > 1 else [],
        "watched": bool(entry.get("is_watched")),
    }


def build_person_screen(request, source, person_id) -> dict | object:
    """Return the person page for the web, or the page's 400 response."""
    from django.http import HttpResponse

    from app.people_views import build_person_context

    context = build_person_context(request, source, person_id)
    if isinstance(context, HttpResponse):
        return context
    person = context["person"]
    user = request.user
    born = None
    if person.get("birth_date"):
        birth = user_tags.user_date_format(person["birth_date"], user)
        if person.get("death_date"):
            born = f"{birth} – {user_tags.user_date_format(person['death_date'], user)}"  # noqa: RUF001  # the page's en dash
        else:
            born = f"Born {birth}"
        if context.get("person_age") is not None:
            born += f" ({context['person_age']})"
    watched = context.get("watched_filmography") or []
    return {
        "name": _text(person.get("name")),
        "image": app_tags.image_url(person.get("image") or settings.IMG_NONE),
        "department": _text(person.get("known_for_department")) or None,
        "born": born,
        "place_of_birth": _text(person.get("place_of_birth")) or None,
        "is_author": bool(context.get("is_author")),
        "stats": {
            "titles": len(watched),
            "movies": context.get("watched_movie_count") or 0,
            "shows": context.get("watched_show_count") or 0,
            "books": context.get("watched_book_count") or 0,
            "together": _text(context.get("tracked_hours_count")) or None,
        },
        "history_url": context.get("history_filter_url") or None,
        "source_url": context.get("source_url") or None,
        "source_label": _text(app_tags.source_readable(context.get("source"))),
        "biography": strip_tags(_text(person.get("biography"))).strip(),
        "watched": [_card(entry, watched=True) for entry in watched],
        "known_for": [
            _card(entry, watched=bool(entry.get("is_watched")))
            for entry in context.get("known_for") or []
        ],
        "filmography": [_credit(entry) for entry in context.get("filmography") or []],
    }


class PersonScreenStatsSerializer(serializers.Serializer):
    """Your numbers with this person."""

    titles = serializers.IntegerField()
    movies = serializers.IntegerField()
    shows = serializers.IntegerField()
    books = serializers.IntegerField()
    together = serializers.CharField(allow_null=True, help_text="Time watched together.")


class PersonScreenCardSerializer(serializers.Serializer):
    """A credit's poster card."""

    title = serializers.CharField()
    url = serializers.CharField()
    poster = serializers.CharField()
    year = serializers.CharField(allow_blank=True)
    media_type = serializers.CharField(allow_blank=True)
    watched = serializers.BooleanField()


class PersonScreenCreditSerializer(serializers.Serializer):
    """A filmography row."""

    title = serializers.CharField()
    url = serializers.CharField()
    thumb = serializers.CharField()
    year = serializers.CharField(allow_blank=True)
    role = serializers.CharField(allow_blank=True)
    media_type = serializers.CharField(allow_blank=True)
    type_label = serializers.CharField(allow_blank=True)
    departments = serializers.ListField(
        child=serializers.CharField(), help_text="Every department, when more than one."
    )
    watched = serializers.BooleanField()


class PersonScreenSerializer(serializers.Serializer):
    """The person page."""

    name = serializers.CharField()
    image = serializers.CharField()
    department = serializers.CharField(allow_null=True)
    born = serializers.CharField(allow_null=True, help_text='"Born <date> (<age>)" or a range.')
    place_of_birth = serializers.CharField(allow_null=True)
    is_author = serializers.BooleanField()
    stats = PersonScreenStatsSerializer()
    history_url = serializers.CharField(allow_null=True)
    source_url = serializers.CharField(allow_null=True)
    source_label = serializers.CharField(allow_blank=True)
    biography = serializers.CharField(allow_blank=True)
    watched = PersonScreenCardSerializer(many=True)
    known_for = PersonScreenCardSerializer(many=True)
    filmography = PersonScreenCreditSerializer(many=True, help_text="Newest first, as the page.")
