"""The web Calendar screen (v2 P4-F).

`GET /api/v1/calendar/screen/` reads the Django Calendar page's own context
(`build_calendar_context`): the month's releases by local day, the month
grid, and the filter and export options. Each release is written as the
page's rows write it (ct/calendar_agenda.html, calendar_list.html).
"""

from __future__ import annotations

from django.urls import reverse
from rest_framework import serializers

from app.models import Status
from app.templatetags import app_tags


def _label(media_type) -> str:
    try:
        return str(app_tags.media_type_readable(media_type))
    except ValueError:
        return str(media_type)


def _plural(media_type) -> str:
    try:
        return str(app_tags.media_type_readable_plural(media_type))
    except (ValueError, KeyError):
        return _label(media_type)


def _status_label(status) -> str:
    try:
        return str(Status(status).label)
    except ValueError:
        return str(status)


def _release(release, user) -> dict:
    item = release.item
    return {
        "id": release.id,
        "media_type": item.media_type,
        "type_label": _label(item.media_type),
        "status": str(getattr(release, "status", None) or ""),
        "title": str(item),
        "code": str(release.readable_content_number or ""),
        "label": str(release),
        "time": str(app_tags.user_event_time(release, user) or ""),
        "poster": str(app_tags.image_url(app_tags.tmdb_size(app_tags.ct_poster(item), "w154")) or ""),
        "image": str(app_tags.image_url(item.image) or ""),
        "href": str(app_tags.media_url(item) or ""),
        "color": str(app_tags.media_color(item.media_type) or ""),
    }


def build_calendar_screen(request) -> dict:
    """Return the Calendar screen for the web from the page's context."""
    from events.views import build_calendar_context

    context = build_calendar_context(request)
    user = request.user
    today = context["today"]
    month, year = context["month"], context["year"]
    enabled = [
        media_type
        for media_type in context["media_types"]
        if getattr(user, f"{media_type}_enabled", False)
    ]
    return {
        "user_id": user.id,
        "view": str(context.get("view_type") or "grid"),
        "year": year,
        "month": month,
        "month_name": str(context["month_name"]),
        "prev": {"year": context["prev_year"], "month": context["prev_month"]},
        "next": {"year": context["next_year"], "month": context["next_month"]},
        "today": {"year": today.year, "month": today.month, "day": today.day},
        "selected_day": int(context.get("selected_day") or 1),
        "weekdays": [str(day) for day in context["weekday_headers"]],
        "weeks": context["calendar"],
        "days": [
            {"day": day, "releases": [_release(release, user) for release in releases]}
            for day, releases in sorted(context["release_dict"].items())
        ],
        "filter_types": [
            {
                "value": media_type,
                "label": _label(media_type),
                "in_month": media_type in context["available_media_types"],
                "statuses": [
                    {"value": status, "label": _status_label(status)}
                    for status in context["filter_statuses_by_type"].get(media_type, [])
                ],
                "month_statuses": list(context["available_statuses_by_type"].get(media_type, [])),
            }
            for media_type in context["filter_media_types"]
        ],
        "reload_url": reverse("reload_calendar"),
        "export": {
            "url": request.build_absolute_uri(
                reverse("download_calendar", kwargs={"token": user.calendar_token})
            ),
            "types": [
                {"value": media_type, "label": _plural(media_type), "enabled": media_type in enabled}
                for media_type in context["media_types"]
            ],
            "statuses": [
                {"value": status, "label": str(app_tags.media_status_readable(status))}
                for status in context["event_statuses"]
            ],
        },
    }


class CalendarChoiceSerializer(serializers.Serializer):
    """A value and its label."""

    value = serializers.CharField()
    label = serializers.CharField()


class CalendarMonthSerializer(serializers.Serializer):
    """A month to navigate to."""

    year = serializers.IntegerField()
    month = serializers.IntegerField()


class CalendarTodaySerializer(serializers.Serializer):
    """Today in the user's time zone."""

    year = serializers.IntegerField()
    month = serializers.IntegerField()
    day = serializers.IntegerField()


class CalendarReleaseSerializer(serializers.Serializer):
    """One release, as the page's rows write it."""

    id = serializers.IntegerField()
    media_type = serializers.CharField()
    type_label = serializers.CharField()
    status = serializers.CharField(allow_blank=True, help_text="The title's status, for the status filter.")
    title = serializers.CharField()
    code = serializers.CharField(allow_blank=True, help_text="E5, #12, ...")
    label = serializers.CharField(help_text="Title and code, as the month grid's cell.")
    time = serializers.CharField(allow_blank=True, help_text="'at 21:00'; empty without a time.")
    poster = serializers.CharField(allow_blank=True)
    image = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True, help_text="The title's Django page.")
    color = serializers.CharField(allow_blank=True)


class CalendarDaySerializer(serializers.Serializer):
    """A day of the month that has releases."""

    day = serializers.IntegerField()
    releases = CalendarReleaseSerializer(many=True)


class CalendarFilterTypeSerializer(serializers.Serializer):
    """A media type the page's filter offers."""

    value = serializers.CharField()
    label = serializers.CharField()
    in_month = serializers.BooleanField(help_text="It has releases this month.")
    statuses = CalendarChoiceSerializer(many=True, help_text="Its status submenu; empty for TV.")
    month_statuses = serializers.ListField(child=serializers.CharField())


class CalendarExportTypeSerializer(serializers.Serializer):
    """A media type the export link can include."""

    value = serializers.CharField()
    label = serializers.CharField()
    enabled = serializers.BooleanField(help_text="On by default (the user's enabled types).")


class CalendarExportSerializer(serializers.Serializer):
    """The iCal export link's options."""

    url = serializers.CharField(help_text="Add media_types and status params, repeated.")
    types = CalendarExportTypeSerializer(many=True)
    statuses = CalendarChoiceSerializer(many=True)


class CalendarScreenSerializer(serializers.Serializer):
    """The Calendar page for one month."""

    user_id = serializers.IntegerField(help_text="Keys the page's saved filter (localStorage).")
    view = serializers.ChoiceField(choices=["grid", "list"])
    year = serializers.IntegerField()
    month = serializers.IntegerField()
    month_name = serializers.CharField()
    prev = CalendarMonthSerializer()
    next = CalendarMonthSerializer()
    today = CalendarTodaySerializer()
    selected_day = serializers.IntegerField()
    weekdays = serializers.ListField(child=serializers.CharField())
    weeks = serializers.ListField(
        child=serializers.ListField(child=serializers.IntegerField()), help_text="0 pads a week."
    )
    days = CalendarDaySerializer(many=True)
    filter_types = CalendarFilterTypeSerializer(many=True)
    reload_url = serializers.CharField(help_text="POST (form, CSRF) to queue Fetch New Releases.")
    export = CalendarExportSerializer()
