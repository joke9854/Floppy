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

# The types the page's standard dialog (fill_track.html) edits. Music and
# podcasts have their own dialogs.
TRACK_SCREEN_TYPES = (
    MediaTypes.MOVIE.value,
    MediaTypes.TV.value,
    MediaTypes.SEASON.value,
    MediaTypes.EPISODE.value,
    MediaTypes.ANIME.value,
    MediaTypes.MANGA.value,
    MediaTypes.GAME.value,
    MediaTypes.BOOK.value,
    MediaTypes.COMIC.value,
    MediaTypes.COMIC_ISSUE.value,
    MediaTypes.BOARDGAME.value,
)
# Music artists and albums (`/track/artist|album/music/<id>/`) and podcast
# shows (`/track/podcast/<source>/<podcast_uuid>/`): their own trackers, in
# the page's shared tracker dialog (v2 P4-D2b).
TRACKER_SCREEN_TYPES = ("artist", "album", MediaTypes.PODCAST.value)
TRACKER_MUSIC_SOURCE = "music"
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


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _plays(context) -> dict | None:
    """Return the Episode Plays tab (fill_track_episode_bulk.html), or None.

    Shows, seasons, grouped anime and podcast shows post it to
    `episode_bulk_save`, artists and albums to `music_bulk_save`; both queue a
    background job that writes the plays.
    """
    if not context.get("episode_plays_tab_available"):
        return None
    form = context["episode_plays_form"]
    domain = context.get("episode_plays_domain") or {}

    def side(prefix):
        return {
            "season_number": _as_int(form[f"{prefix}_season_number"].value()),
            "episode_number": _as_int(form[f"{prefix}_episode_number"].value()),
        }

    return {
        "tab_label": str(_(context.get("episode_plays_tab_label") or "Episode Plays")),
        "submit_label": str(_(context.get("episode_plays_submit_label") or "Save plays")),
        "save_url": str(context["episode_plays_formaction"]),
        "mode_notice": str(context.get("episode_plays_mode_notice") or ""),
        "hidden": [_field(bound) for bound in form.hidden_fields()],
        "first": side("first"),
        "last": side("last"),
        "write_mode": _field(form["write_mode"]),
        "distribution_mode": _field(form["distribution_mode"]),
        "start_date": _field(form["start_date"]),
        "end_date": _field(form["end_date"]),
        "seasons": [
            {"season_number": season["season_number"], "season_title": str(season["season_title"])}
            for season in domain.get("seasons", [])
        ],
        "episodes": {
            str(season_number): [
                {
                    "order": episode["order"],
                    "season_number": episode["season_number"],
                    "episode_number": episode["episode_number"],
                    "episode_title": str(episode.get("episode_title") or ""),
                    "selector_label": str(episode.get("selector_label") or ""),
                    "existing_play_count": episode.get("existing_play_count") or 0,
                    "runtime_minutes": _as_int(episode.get("runtime_minutes")),
                    "air_date": str(episode.get("air_date") or ""),
                }
                for episode in episodes
            ]
            for season_number, episodes in (domain.get("seasonEpisodeMap") or {}).items()
        },
        "locked_season_number": _as_int(domain.get("lockedSeasonNumber")),
        "hide_season_selectors": bool(domain.get("hideSeasonSelectors")),
        "labels": {
            key: str(domain.get(name) or "")
            for key, name in (
                ("first_selection", "firstSelectionTitle"),
                ("last_selection", "lastSelectionTitle"),
                ("season_field", "seasonFieldLabel"),
                ("episode_field", "episodeFieldLabel"),
                ("noun", "selectionNoun"),
                ("noun_plural", "selectionNounPlural"),
                ("target", "distributionTargetLabel"),
                ("date_shortcut", "dateShortcutLabel"),
            )
        },
        "missing_target_fallback": str(domain.get("missingTargetDateFallbackDistribution") or ""),
    }


def _discover(context) -> dict | None:
    """Return the Discover tab (discover_tab_content.html), or None."""
    item = context.get("metadata_item")
    if not context.get("discover_tab_available") or item is None:
        return None
    return {
        "item_id": item.id,
        "hidden": bool(context.get("is_hidden_from_discover")),
        "save_url": reverse("discover_toggle_hidden"),
    }


def _collection_kind(bound) -> str:
    """Return how the web draws a CollectionEntryForm field.

    The form swaps configured fields to a Select widget but keeps the
    CharField, so the choices live on the widget, not the field.
    """
    widget = bound.field.widget
    input_type = getattr(widget, "input_type", None)
    if bound.name == "collected_at":
        return "datetime" if settings.TRACK_TIME else "date"
    if input_type == "checkbox":
        return "checkbox"
    if input_type == "select" or hasattr(widget, "choices"):
        return "select"
    if input_type == "number":
        return "number"
    return "text"


def _collection_field(bound) -> dict:
    kind = _collection_kind(bound)
    attrs = bound.field.widget.attrs
    value = bound.value()
    if kind == "checkbox":
        value = "on" if value else ""
    elif kind in {"datetime", "date", "select"}:
        value = "" if value is None else str(value)
    else:
        formatted = bound.field.widget.format_value(value)
        value = "" if formatted is None else str(formatted)
    return {
        "name": bound.name,
        "label": str(_(bound.label)) if bound.label else "",
        "kind": kind,
        "value": value,
        "choices": [
            {"value": "" if choice is None else str(choice), "label": str(_(str(label)))}
            for choice, label in bound.field.widget.choices
        ]
        if kind == "select"
        else [],
        "required": bool(bound.field.required),
        "min": str(attrs["min"]) if "min" in attrs else None,
        "max": str(attrs["max"]) if "max" in attrs else None,
        "step": str(attrs["step"]) if "step" in attrs else None,
        "placeholder": str(attrs.get("placeholder") or ""),
        "help_text": str(bound.help_text or ""),
    }


def _collection_entry_lines(entry) -> list[str]:
    """Return an existing copy's summary lines, as the dialog's copies list.

    collection_entry_summary.html writes them there without the date, the
    source labels or the game layout.
    """
    lines = [
        _("Format: %(value_1)s") % {"value_1": app_tags.title_preserve_acronyms(entry.media_type)}
        if entry.media_type
        else str(_("Collected"))
    ]
    quality = [
        part
        for part in (
            entry.resolution,
            entry.hdr,
            entry.audio_codec,
            entry.audio_channels,
            (_("%(value_1)s kbps") % {"value_1": entry.bitrate}) if entry.bitrate else "",
            str(_("3D")) if entry.is_3d else "",
        )
        if part
    ]
    if quality:
        lines.append(" • ".join(str(part) for part in quality))
    purchase = [
        part
        for part in (
            f"${entry.purchase_price:.2f}" if entry.purchase_price else "",
            entry.purchase_location or "",
        )
        if part
    ]
    if purchase:
        lines.append(" • ".join(purchase))
    return [str(line) for line in lines]


def _custom_field(field, stored) -> dict:
    kind = field.field_type
    if kind == "checkbox":
        value = "on" if stored is True else ""
    elif kind == "number" and isinstance(stored, float) and stored.is_integer():
        value = str(int(stored))
    else:
        value = "" if stored is None else str(stored)
    return {
        "name": f"custom_field_{field.id}",
        "label": field.label,
        "kind": kind,
        "value": value,
        "choices": (
            [{"value": "", "label": str(_("Select"))}]
            + [{"value": str(option), "label": str(option)} for option in field.options or []]
        )
        if kind == "select"
        else [],
        "required": False,
        "min": None,
        "max": None,
        "step": "any" if kind == "number" else None,
        "placeholder": "",
        "help_text": "",
    }


def _collection(context) -> dict | None:
    """Return the Collection tab (collection_modal.html), or None.

    The dialog has it for a single episode only, so the season and episode
    audit lists the show and season modals carry are always empty here.
    """
    collection = context.get("collection_context")
    if not context.get("collection_tab_available") or collection is None:
        return None
    form = collection["form"]
    item = collection["item"]
    configured = collection.get("collection_fields") or []
    fields = [
        _collection_field(bound)
        for bound in form
        if bound.name != "item" and (not configured or bound.name in configured)
    ]
    stored = collection.get("entry_custom_field_values") or {}
    return_url = collection.get("return_url") or ""
    next_query = f"?next={quote(return_url, safe='')}" if return_url else ""
    entries = collection.get("visible_existing_entries") or []
    return {
        "item_id": item.id,
        "save_url": reverse("collection_add") + next_query,
        "add_label": str(_("Add Another Copy") if entries else _("Add Copy")),
        "fields": fields,
        "custom_groups": [
            {
                "name": group.name,
                "fields": [_custom_field(field, stored.get(str(field.id))) for field in group.visible_fields],
            }
            for group in collection.get("custom_field_groups") or []
        ],
        "entries": [
            {
                "id": entry.id,
                "lines": _collection_entry_lines(entry),
                "remove_url": reverse("collection_remove", args=[entry.id]),
            }
            for entry in entries
        ],
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
        "plays": _plays(context),
        "discover": _discover(context),
        "collection": _collection(context),
    }


def _suggestion(context) -> dict:
    suggestion = context.get("date_suggestion") or {}
    return {
        "label": str(_(suggestion.get("label") or "")) if suggestion.get("date") else "",
        "date": str(suggestion.get("date") or ""),
        "runtime_minutes": int(suggestion["runtime_minutes"])
        if str(suggestion.get("runtime_minutes") or "").isdigit()
        else None,
    }


def tracker_context(request, media_type, source, media_id):
    """Return the page's tracker dialog context, or None for no such tracker.

    Artists and albums are addressed by their own id with the source `music`;
    a podcast by its show's `podcast_uuid`, as the Library's podcast card
    opens it (an episode's uuid opens the page's episode dialog: None).
    """
    from app.models import PodcastShow

    if media_type in ("artist", "album"):
        if source != TRACKER_MUSIC_SOURCE or not str(media_id).isdigit():
            return None
        if media_type == "artist":
            from app.music_views import build_artist_track_context

            return build_artist_track_context(request, int(media_id))
        from app.music_album_views import build_album_track_context

        return build_album_track_context(request, int(media_id))
    show = PodcastShow.objects.filter(podcast_uuid=media_id, source=source).first()
    if show is None:
        return None
    from app.track_modal_views import build_podcast_show_track_context

    return build_podcast_show_track_context(request, show)


def build_tracker_screen(request, media_type, context):
    """Return an artist's, album's or podcast show's track dialog for the web."""
    form = context["form"]
    tracker = context["media"]

    def action(key):
        # The page's formaction carries `?next=<return_url>`; the web reads JSON.
        return str(context.get(key) or "").split("?", 1)[0]

    return {
        "media_type": media_type,
        "title": str(context["title"]),
        "subtitle": "",
        "tracked": tracker is not None,
        "track_time": bool(settings.TRACK_TIME),
        "max_progress": None,
        "hidden": [_field(bound) for bound in context["general_hidden_fields"]],
        "fields": [_field(bound) for bound in context["general_fields"]],
        "notes": _field(form["notes"]) if "notes" in form.fields else None,
        "koreader": None,
        "date_suggestion": _suggestion(context),
        "week_start": str(getattr(request.user, "week_start_day", "") or ""),
        "save_url": action("general_submit_formaction"),
        "delete_url": action("general_delete_formaction") if tracker is not None else "",
        "save_as_new": "",
        "rewatch": None,
        "page_url": "",
        "plays": _plays(context),
        "discover": None,
        "collection": None,
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
        choices=["hidden", "select", "number", "datetime", "date", "textarea", "text", "checkbox"],
        help_text="A checkbox posts its name only when ticked (value `on`).",
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


class TrackPlaysSideSerializer(serializers.Serializer):
    """The first or last episode of the range."""

    season_number = serializers.IntegerField(allow_null=True)
    episode_number = serializers.IntegerField(allow_null=True)


class TrackPlaysSeasonSerializer(serializers.Serializer):
    """A season the range can start or end in."""

    season_number = serializers.IntegerField()
    season_title = serializers.CharField(allow_blank=True)


class TrackPlaysEpisodeSerializer(serializers.Serializer):
    """An episode (or track) of the range, in watch order."""

    order = serializers.IntegerField(help_text="The range runs from the first's order to the last's.")
    season_number = serializers.IntegerField()
    episode_number = serializers.IntegerField()
    episode_title = serializers.CharField(allow_blank=True)
    selector_label = serializers.CharField(allow_blank=True)
    existing_play_count = serializers.IntegerField()
    runtime_minutes = serializers.IntegerField(allow_null=True)
    air_date = serializers.CharField(allow_blank=True, help_text="ISO date; empty when unknown.")


class TrackPlaysLabelsSerializer(serializers.Serializer):
    """The tab's wording for this kind of title (episodes, tracks)."""

    first_selection = serializers.CharField(allow_blank=True)
    last_selection = serializers.CharField(allow_blank=True)
    season_field = serializers.CharField(allow_blank=True)
    episode_field = serializers.CharField(allow_blank=True)
    noun = serializers.CharField(allow_blank=True)
    noun_plural = serializers.CharField(allow_blank=True)
    target = serializers.CharField(allow_blank=True)
    date_shortcut = serializers.CharField(allow_blank=True)


class TrackPlaysSerializer(serializers.Serializer):
    """The Episode Plays tab: log plays over a range of episodes or tracks."""

    tab_label = serializers.CharField()
    submit_label = serializers.CharField()
    save_url = serializers.CharField(
        help_text="Post hidden, the four range numbers, write_mode, distribution_mode, "
        "start_date, end_date and episode_count with `Accept: application/json`; "
        "the plays are written by a background job."
    )
    mode_notice = serializers.CharField(allow_blank=True)
    hidden = TrackFieldSerializer(many=True, help_text="Post back unchanged.")
    first = TrackPlaysSideSerializer()
    last = TrackPlaysSideSerializer()
    write_mode = TrackFieldSerializer()
    distribution_mode = TrackFieldSerializer()
    start_date = TrackFieldSerializer()
    end_date = TrackFieldSerializer()
    seasons = TrackPlaysSeasonSerializer(many=True)
    episodes = serializers.DictField(
        child=TrackPlaysEpisodeSerializer(many=True), help_text="By season number."
    )
    locked_season_number = serializers.IntegerField(allow_null=True)
    hide_season_selectors = serializers.BooleanField()
    labels = TrackPlaysLabelsSerializer()
    missing_target_fallback = serializers.CharField(
        allow_blank=True,
        help_text='"even" when saving falls back to an even spread for items without a date.',
    )


class TrackDiscoverSerializer(serializers.Serializer):
    """The Discover tab: whether Discover recommends this title."""

    item_id = serializers.IntegerField()
    hidden = serializers.BooleanField(help_text="Hidden from Discover (Not interested).")
    save_url = serializers.CharField(
        help_text="Post item_id and action (hide or unhide) with `Accept: application/json`."
    )


class TrackCollectionEntrySerializer(serializers.Serializer):
    """An owned copy of the episode."""

    id = serializers.IntegerField()
    lines = serializers.ListField(child=serializers.CharField(), help_text="The page's summary lines.")
    remove_url = serializers.CharField(help_text="POST with `Accept: application/json` to remove the copy.")


class TrackCollectionGroupSerializer(serializers.Serializer):
    """One of the user's custom collection field groups."""

    name = serializers.CharField()
    fields = TrackFieldSerializer(many=True)


class TrackCollectionSerializer(serializers.Serializer):
    """The Collection tab: the episode's owned copies and the Add Copy form."""

    item_id = serializers.IntegerField(help_text="Post as item_id with the form.")
    save_url = serializers.CharField(
        help_text="POST item_id, the fields and the custom fields here with `Accept: application/json`."
    )
    add_label = serializers.CharField()
    fields = TrackFieldSerializer(many=True, help_text="In the page's order; the first is full width.")
    custom_groups = TrackCollectionGroupSerializer(many=True)
    entries = TrackCollectionEntrySerializer(many=True)


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
    plays = TrackPlaysSerializer(allow_null=True, help_text="The Episode Plays tab, where the page has it.")
    discover = TrackDiscoverSerializer(allow_null=True, help_text="The Discover tab, where the page has it.")
    collection = TrackCollectionSerializer(allow_null=True, help_text="The Collection tab (single episodes).")
