"""The web studio page's data (v2 P4-L3b): the Django studio page, as JSON.

`app.people_data.build_studio_page` is the page's own builder, so this shows
the same studio, numbers and credited titles as /studio/...; cards are the
person page's cards plus the user's own status for the title.
"""

from __future__ import annotations

from django.apps import apps
from rest_framework import serializers

from app.models import Media, Status
from app.templatetags import app_tags
from users.templatetags import user_tags

from .person_screen import PersonScreenCardSerializer, _card, _text


def _statuses(user, source, entries) -> dict[tuple[str, str], str]:
    """Return the user's tracked status per (media type, media id) of the entries."""
    wanted: dict[str, set[str]] = {}
    for entry in entries:
        if entry.get("media_id") is not None and entry.get("media_type"):
            wanted.setdefault(entry["media_type"], set()).add(str(entry["media_id"]))
    statuses = {}
    for media_type, ids in wanted.items():
        try:
            model = apps.get_model("app", media_type)
        except LookupError:
            continue
        if not issubclass(model, Media):
            continue
        rows = model.objects.filter(
            user=user, item__source=source, item__media_id__in=ids
        ).values_list("item__media_id", "status")
        for media_id, status in rows:
            statuses[(media_type, str(media_id))] = status
    return statuses


def build_studio_screen(request, source, studio_id) -> dict:
    """Return the studio page for the web; raises Http404 for an unknown studio."""
    from app.people_data import build_studio_page

    page = build_studio_page(source, studio_id)
    studio = page["studio"]
    user = request.user
    entries = page["credited_titles"]
    statuses = _statuses(user, source, entries)
    media_type = page["credited_media_type"]
    label = (
        _text(app_tags.media_type_readable_plural(media_type))
        if media_type
        else "Titles"
    )

    cards = []
    for entry in entries:
        key = (entry.get("media_type"), str(entry.get("media_id")))
        status = statuses.get(key)
        card = _card(
            {**entry, "source": entry.get("source") or source},
            watched=status == Status.COMPLETED.value,
        )
        tracked = entry.get("tracked_item")
        if tracked is not None:
            card["url"] = app_tags.media_url(tracked)
        card["status"] = status
        cards.append(card)

    counts = [{"label": label, "value": len(entries)}]
    for key, name in (
        ("studio_developed_count", "Developed"),
        ("studio_published_count", "Published"),
    ):
        if page[key] is not None:
            counts.append({"label": name, "value": page[key]})
    founded = page["studio_founded"]
    return {
        "studio": {
            "name": _text(studio.name),
            "image": app_tags.image_url(studio.logo) if studio.logo else None,
            "description": _text(page["studio_description"]),
            "source_label": _text(app_tags.source_readable(source)),
            "source_url": page["studio_source_url"] or None,
            "founded": (_text(user_tags.user_date_format(founded, user)) or None)
            if founded
            else None,
            "counts": counts,
        },
        "sections": [{"label": label, "cards": cards}],
    }


class StudioScreenCardSerializer(PersonScreenCardSerializer):
    """A credited title's poster card, with your status for it."""

    status = serializers.CharField(allow_null=True, help_text="Your tracked status, if any.")


class StudioScreenCountSerializer(serializers.Serializer):
    """One of the studio's numbers."""

    label = serializers.CharField()
    value = serializers.IntegerField()


class StudioScreenStudioSerializer(serializers.Serializer):
    """The studio's profile."""

    name = serializers.CharField()
    image = serializers.CharField(allow_null=True, help_text="The logo; null without one.")
    description = serializers.CharField(allow_blank=True)
    source_label = serializers.CharField(allow_blank=True)
    source_url = serializers.CharField(allow_null=True, help_text="The studio's website.")
    founded = serializers.CharField(allow_null=True, help_text="In the user's date format.")
    counts = StudioScreenCountSerializer(many=True)


class StudioScreenSectionSerializer(serializers.Serializer):
    """A group of credited titles."""

    label = serializers.CharField()
    cards = StudioScreenCardSerializer(many=True)


class StudioScreenSerializer(serializers.Serializer):
    """The studio page."""

    studio = StudioScreenStudioSerializer()
    sections = StudioScreenSectionSerializer(many=True)
