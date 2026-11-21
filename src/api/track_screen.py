"""The web app's track dialog, General tab (v2 P4-D1): the page's own form.

`app.track_modal_views.build_standard_track_context` is the Django track
modal's builder (fill_track.html), so the fields, their order, choices,
values and limits are the page's. The web posts the form back to the page's
own endpoints (`media_save`, `episode_save`, `media_delete`,
`media_rewatch`) with `Accept: application/json`, so saving keeps one
implementation.

Dates are sent as the page's hidden input holds them before its picker
normalises them: the form's value in the server's time zone, microseconds
included, so posting an untouched date back stores the same instant.
"""

from __future__ import annotations

from urllib.parse import quote

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from app.models import MediaTypes
from app.templatetags import app_tags

TRACK_SCREEN_TYPES = (
    MediaTypes.MOVIE.value,
    MediaTypes.TV.value,
    MediaTypes.SEASON.value,
    MediaTypes.EPISODE.value,
)
_DATE_FIELDS = ("start_date", "end_date")


def _kind(bound) -> str:
    """Return how the web draws a field, from the widget the page renders."""
    widget = bound.field.widget
    if bound.name in _DATE_FIELDS:
        return "datetime" if settings.TRACK_TIME else "date"
    if bound.is_hidden:
        return "hidden"
    if getattr(widget, "input_type", None) == "number":
        return "number"
    if getattr(widget, "allow_multiple_selected", None) is not None or hasattr(widget, "choices"):
        return "select"
    if widget.__class__.__name__ == "Textarea":
        return "textarea"
    return "text"


def _value(bound) -> str:
    """Return the value as the page's input holds it."""
    value = bound.value()
    if value is None:
        return ""
    if bound.name in _DATE_FIELDS or _kind(bound) == "select":
        # The picker's hidden input takes `field.value` as text (str of the
        # naive server-time datetime, microseconds included); a select's
        # format_value is a list of the selected values.
        return str(value)
    formatted = bound.field.widget.format_value(value)
    return "" if formatted is None else str(formatted)


def _field(bound) -> dict:
    attrs = bound.field.widget.attrs
    choices = []
    if _kind(bound) == "select":
        choices = [
            {"value": "" if value is None else str(value), "label": str(label)}
            for value, label in bound.field.choices
        ]
    return {
        "name": bound.name,
        "label": str(_(bound.label)) if bound.label else "",
        "kind": _kind(bound),
        "value": _value(bound),
        "choices": choices,
        "required": bool(bound.field.required),
        "min": str(attrs["min"]) if "min" in attrs else None,
        "max": str(attrs["max"]) if "max" in attrs else None,
        "step": str(attrs["step"]) if "step" in attrs else None,
        "placeholder": str(attrs.get("placeholder") or ""),
        "help_text": str(bound.help_text or ""),
    }


def build_track_screen(request, media_type, source, media_id, season_number=None, episode_number=None):
    """Return the track dialog's General tab for the web."""
    from app.track_modal_views import build_standard_track_context

    context = build_standard_track_context(
        request,
        source,
        media_type,
        media_id,
        season_number,
        episode_number,
    )
    form = context["form"]
    media = context["media"]
    metadata_item = context.get("metadata_item")
    next_url = app_tags.media_url(metadata_item) if metadata_item is not None else ""
    query = f"?next={quote(next_url, safe='')}" if next_url else ""
    rewatch_action = context.get("general_rewatch_action") or ""
    started = context.get("general_rewatch_started_at")
    suggestion = context.get("date_suggestion") or {}
    return {
        "media_type": media_type,
        "title": str(context["title"]),
        "subtitle": str(context.get("title_subtitle") or ""),
        "tracked": media is not None,
        "track_time": bool(settings.TRACK_TIME),
        "max_progress": context.get("max_progress"),
        "hidden": [_field(bound) for bound in context["general_hidden_fields"]],
        "fields": [_field(bound) for bound in context["general_fields"]],
        "notes": _field(form["notes"]) if "notes" in form.fields else None,
        "koreader": (
            {"value": context.get("koreader_document_id") or ""}
            if context.get("show_koreader_document_field")
            else None
        ),
        "date_suggestion": {
            "label": str(_(suggestion.get("label") or "")) if suggestion.get("date") else "",
            "date": str(suggestion.get("date") or ""),
            "runtime_minutes": int(suggestion["runtime_minutes"])
            if str(suggestion.get("runtime_minutes") or "").isdigit()
            else None,
        },
        "week_start": str(getattr(request.user, "week_start_day", "") or ""),
        "save_url": (
            reverse("episode_save") if media_type == MediaTypes.EPISODE.value else reverse("media_save")
        )
        + query,
        "delete_url": (reverse("media_delete") + query) if media is not None else "",
        "save_as_new": (
            (
                _("Save as another play")
                if media_type == MediaTypes.MOVIE.value
                else _("Save as new entry")
            )
            if context.get("episode_save_as_new")
            else ""
        ),
        "rewatch": (
            {
                "action": rewatch_action,
                "label": str(_(context.get("general_rewatch_label") or "")),
                "url": f"{reverse('media_rewatch')}?action={rewatch_action}"
                + (f"&next={quote(next_url, safe='')}" if next_url else ""),
                "started_at": started.isoformat() if started else None,
            }
            if rewatch_action
            else None
        ),
        "page_url": next_url,
    }


class TrackFieldChoiceSerializer(serializers.Serializer):
    """A select option."""

    value = serializers.CharField(allow_blank=True)
    label = serializers.CharField(allow_blank=True)


class TrackFieldSerializer(serializers.Serializer):
    """One form field, as the page renders it; post `name=value` back."""

    name = serializers.CharField()
    label = serializers.CharField(allow_blank=True)
    kind = serializers.ChoiceField(
        choices=["hidden", "select", "number", "datetime", "date", "textarea", "text"]
    )
    value = serializers.CharField(
        allow_blank=True,
        help_text=(
            "The value as the page's input holds it. Dates are the server-time "
            "value with microseconds; post them back unchanged to keep the instant."
        ),
    )
    choices = TrackFieldChoiceSerializer(many=True)
    required = serializers.BooleanField()
    min = serializers.CharField(allow_null=True)
    max = serializers.CharField(allow_null=True)
    step = serializers.CharField(allow_null=True)
    placeholder = serializers.CharField(allow_blank=True)
    help_text = serializers.CharField(allow_blank=True)


class TrackKoreaderSerializer(serializers.Serializer):
    """The KOReader document ID field (books, with KOReader connected)."""

    value = serializers.CharField(allow_blank=True)


class TrackDateSuggestionSerializer(serializers.Serializer):
    """The pickers' Release Date shortcut."""

    label = serializers.CharField(allow_blank=True)
    date = serializers.CharField(allow_blank=True, help_text="An ISO date; empty when unknown.")
    runtime_minutes = serializers.IntegerField(
        allow_null=True, help_text="Start = end minus this, when the end date is set from it."
    )


class TrackRewatchSerializer(serializers.Serializer):
    """Rewatch or End rewatch, for a finished or rewatching show or season."""

    action = serializers.ChoiceField(choices=["start", "stop"])
    label = serializers.CharField()
    url = serializers.CharField(help_text="POST the form here; `rewatch_started_at` for start.")
    started_at = serializers.CharField(allow_null=True)


class TrackScreenSerializer(serializers.Serializer):
    """The track dialog's General tab."""

    media_type = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    tracked = serializers.BooleanField(help_text="False: the form adds the title.")
    track_time = serializers.BooleanField(help_text="Dates carry a time (TRACK_TIME).")
    max_progress = serializers.IntegerField(allow_null=True)
    hidden = TrackFieldSerializer(many=True, help_text="Post back unchanged.")
    fields = TrackFieldSerializer(many=True, help_text="In the page's order.")
    notes = TrackFieldSerializer(allow_null=True)
    koreader = TrackKoreaderSerializer(allow_null=True)
    date_suggestion = TrackDateSuggestionSerializer()
    week_start = serializers.CharField(allow_blank=True)
    save_url = serializers.CharField(
        help_text="POST the form here with Accept: application/json."
    )
    delete_url = serializers.CharField(allow_blank=True)
    save_as_new = serializers.CharField(
        allow_blank=True,
        help_text="The label of the second save button (post save_as_new_entry=1); empty when none.",
    )
    rewatch = TrackRewatchSerializer(allow_null=True)
    page_url = serializers.CharField(allow_blank=True, help_text="The title's Django page.")
