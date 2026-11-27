"""Settings > Preferences for the web (v2 P4-J2).

The page posts to the Django `preferences` view, which resets the auto-pause
rules, the provider region and the metadata language when they are missing,
so the screen returns every field as the exact string the form posts
(`values`, keyed by POST name) and the web posts all of them back.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from users import models as user_models

# Example text the Django page shows beside each date and time format.
_DATE_HINTS = {
    "system_default": "Aug 12, 2025 / 12 Aug 2025",
    "iso_8601": "2025-08-12",
    "month_d_yyyy": "Aug 12, 2025",
    "d_mon_yyyy": "12 Aug 2025",
    "m_d_yyyy": "08/12/2025",
    "d_m_yyyy": "12/08/2025",
    "dd_mm_yyyy": "12.08.2025",
    "yyyy_mm_dd": "2025/08/12",
}
_TIME_HINTS = {
    "system_default": "6:45 PM / 18:45",
    "h_mm_ampm": "6:45 PM",
    "hh_mm_ampm": "06:45 PM",
    "hh_mm": "18:45",
    "hh_mm_ss": "18:45:00",
}
_GAME_HINTS = {
    "sessions": "new entry per play; exact history",
    "repeats": "update one entry; spreads time across range",
}


def _choices(pairs, hints=None) -> list[dict]:
    hints = hints or {}
    return [
        {"value": str(value), "label": str(label), "hint": hints.get(str(value), "")}
        for value, label in pairs
    ]


def _bit(value) -> str:
    return "1" if value else "0"


def _select(name, label, note, choices) -> dict:
    return {"name": name, "label": label, "note": note, "kind": "select", "choices": choices}


def _switch(name, label, note) -> dict:
    return {"name": name, "label": label, "note": note, "kind": "switch", "choices": []}


def build_preferences(request) -> dict:
    """Return the Preferences page: sections of fields, values, auto-pause."""
    from users.views import preference_choices

    user = request.user
    choices = preference_choices(user)

    # The Django page offers these date formats; a stored one it no longer
    # lists still shows, so a save keeps it.
    date_formats = [
        (value, label)
        for value, label in user_models.DateFormatChoices.choices
        if value in _DATE_HINTS or value == user.date_format
    ]
    sections = [
        {
            "title": _("Display & Layout"),
            "note": _("Control content display."),
            "fields": [
                _select("date_format", _("Date Format"), _("How dates appear."), _choices(date_formats, _DATE_HINTS)),
                _select(
                    "time_format",
                    _("Time Format"),
                    _("How times appear."),
                    _choices(user_models.TimeFormatChoices.choices, _TIME_HINTS),
                ),
                _select(
                    "mobile_grid_layout",
                    _("Mobile Grid"),
                    _("Mobile column count."),
                    _choices(user_models.MobileGridLayoutChoices.choices),
                ),
                _select(
                    "media_card_subtitle_display",
                    _("Card Subtitles"),
                    _("When subtitles appear."),
                    _choices(user_models.MediaCardSubtitleDisplayChoices.choices),
                ),
                _switch("progress_bar", _("Progress Bar"), _("Show progress on cards.")),
                _select(
                    "title_display_preference",
                    _("Title Display"),
                    _("Card title style."),
                    _choices(user_models.TitleDisplayPreferenceChoices.choices),
                ),
                _select(
                    "top_talent_sort_by",
                    _("Talent Sort"),
                    _("Statistics sort order."),
                    _choices(user_models.TopTalentSortChoices.choices),
                ),
            ],
        },
        {
            "title": _("Language & Metadata"),
            "note": _("Manage languages and providers."),
            "fields": [
                _select(
                    "watch_provider_region",
                    _("Provider Region"),
                    _("Provider region."),
                    _choices(choices["watch_provider_regions"]),
                ),
                _select(
                    "metadata_language",
                    _("Metadata Language"),
                    _("Metadata language."),
                    _choices(choices["metadata_language_choices"]),
                ),
                _select(
                    "ui_language",
                    _("UI Language"),
                    _("Interface display language."),
                    _choices(user_models.UiLanguageChoices.choices),
                ),
            ],
        },
        {
            "title": _("Tracking & Interaction"),
            "note": _("Control how Floppy tracks and interacts with your activity."),
            "fields": [
                _switch("hide_completed_recommendations", _("Hide Completed"), _("Hide completed items.")),
                _select(
                    "rating_scale",
                    _("Rating Scale"),
                    _("Choose whether ratings use a 1-5 or 1-10 scale."),
                    _choices(user_models.RatingScaleChoices.choices),
                ),
                _switch("hide_zero_rating", _("Hide Zero Ratings"), _("Hide zero-value ratings.")),
                _switch(
                    "obfuscate_episodes",
                    _("Blur Unwatched Episode Images"),
                    _("Spoiler protection: blur the stills of episodes you haven't watched."),
                ),
                _switch(
                    "hide_episode_overviews",
                    _("Hide Unwatched Episode Descriptions"),
                    _("Spoiler protection: keep the overview of episodes you haven't watched behind Reveal."),
                ),
                _select(
                    "quick_season_update_mobile",
                    _("Home Buttons"),
                    _("Home card actions."),
                    _choices(user_models.QuickSeasonUpdateChoices.choices),
                ),
                _select(
                    "game_logging_style",
                    _("Game Logging"),
                    _("Game history style."),
                    _choices(user_models.GameLoggingStyleChoices.choices, _GAME_HINTS),
                ),
                _select(
                    "book_comic_manga_progress_percentage",
                    _("Progress Format"),
                    _("Percent or pages."),
                    _choices((("0", _("Pages/Issues/Chapters")), ("1", _("Percentage")))),
                ),
                _select(
                    "session_duration",
                    _("Session Duration"),
                    _("Sign-in timeout."),
                    _choices(user_models.SessionDurationChoices.choices),
                ),
                _select(
                    "scrobble_watched_percent",
                    _("Scrobble Watched Threshold"),
                    _(
                        "How far into a movie or episode an app must be when it stops "
                        "playback for Floppy to mark it watched."
                    ),
                    _choices(user_models.ScrobbleWatchedPercentChoices.choices),
                ),
            ],
        },
    ]
    values = {
        "date_format": user.date_format,
        "time_format": user.time_format,
        "mobile_grid_layout": user.mobile_grid_layout,
        "media_card_subtitle_display": user.media_card_subtitle_display,
        "progress_bar": _bit(user.progress_bar),
        "title_display_preference": user.title_display_preference,
        "top_talent_sort_by": user.top_talent_sort_by,
        "watch_provider_region": user.watch_provider_region,
        "metadata_language": user.metadata_language,
        "ui_language": user.ui_language,
        "hide_completed_recommendations": _bit(user.hide_completed_recommendations),
        "rating_scale": str(user.rating_scale),
        "hide_zero_rating": _bit(user.hide_zero_rating),
        "obfuscate_episodes": _bit(user.obfuscate_episodes),
        "hide_episode_overviews": _bit(user.hide_episode_overviews),
        "quick_season_update_mobile": user.quick_season_update_mobile,
        "game_logging_style": user.game_logging_style,
        "book_comic_manga_progress_percentage": _bit(user.book_comic_manga_progress_percentage),
        "session_duration": str(user.session_duration),
        "scrobble_watched_percent": str(user.scrobble_watched_percent),
    }
    values = {key: "" if value is None else str(value) for key, value in values.items()}
    # A stored value the list does not offer (UNSET before a region is picked,
    # a language TMDB dropped) still shows and posts back unchanged.
    for section in sections:
        for field in section["fields"]:
            stored = values[field["name"]]
            if field["kind"] == "select" and stored not in {choice["value"] for choice in field["choices"]}:
                label = _("Not set") if stored in ("", "UNSET") else stored
                field["choices"].insert(0, {"value": stored, "label": label, "hint": ""})
    return {
        "is_demo": user.is_demo,
        "sections": sections,
        "values": values,
        "auto_pause_rules": [
            {"library": rule["library"], "weeks": int(rule["weeks"])} for rule in (user.auto_pause_rules or [])
        ],
        "auto_pause_libraries": [
            {"value": value, "label": str(label)} for value, label in choices["library_labels"].items()
        ],
        # Region and language keep their stored value when TMDB did not answer.
        "tmdb_lists_loaded": choices["regions_loaded"] and choices["languages_loaded"],
        "save_url": reverse("preferences"),
    }


class SettingsPreferenceChoiceSerializer(serializers.Serializer):
    """One option of a preference."""

    value = serializers.CharField(allow_blank=True)
    label = serializers.CharField()
    hint = serializers.CharField(allow_blank=True)


class SettingsPreferenceFieldSerializer(serializers.Serializer):
    """One preference: a select or a switch (`"1"`/`"0"`), posted as `name`."""

    name = serializers.CharField()
    label = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    kind = serializers.ChoiceField(choices=["select", "switch"])
    choices = SettingsPreferenceChoiceSerializer(many=True)


class SettingsPreferenceSectionSerializer(serializers.Serializer):
    """A group of preferences."""

    title = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    fields = SettingsPreferenceFieldSerializer(many=True)


class SettingsAutoPauseRuleSerializer(serializers.Serializer):
    """Pause in-progress items of `library` after `weeks` without activity."""

    library = serializers.CharField()
    weeks = serializers.IntegerField()


class SettingsAutoPauseLibrarySerializer(serializers.Serializer):
    """A library an auto-pause rule can name (`all`, or a media type)."""

    value = serializers.CharField()
    label = serializers.CharField()


class SettingsPreferencesSerializer(serializers.Serializer):
    """Preferences: post `values`, `auto_pause_enabled` and `auto_pause_rules`."""

    is_demo = serializers.BooleanField()
    sections = SettingsPreferenceSectionSerializer(many=True)
    values = serializers.DictField(child=serializers.CharField(allow_blank=True))
    auto_pause_rules = SettingsAutoPauseRuleSerializer(many=True)
    auto_pause_libraries = SettingsAutoPauseLibrarySerializer(many=True)
    tmdb_lists_loaded = serializers.BooleanField()
    save_url = serializers.CharField()
