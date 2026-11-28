"""The activity sessions dialog's data for the web (v2 P4-L3b).

`app.history_views.build_activity_sessions_context` is the Django dialog's own
builder, so the web shows the same days, filters and stats; rows are written as
the History screen writes them (`api.history_screen.history_day`).
"""

from __future__ import annotations

from django.utils.translation import gettext as _
from rest_framework import serializers

from .history_screen import HistoryScreenDaySerializer, history_day


def build_sessions_screen(request) -> dict:
    """Return the sessions dialog for the web from the Django dialog's context."""
    from app.history_views import (
        SESSION_HISTORY_MAX_DAYS,
        build_activity_sessions_context,
    )

    context = build_activity_sessions_context(request)
    user = request.user
    return {
        "days": [history_day(day, user, "activity") for day in context["history_days"]],
        "stats": [
            {"label": str(_(stat["label"])), "value": str(stat["value"])}
            for stat in context["session_history_stats"]
        ],
        "capped": bool(context["history_capped"]),
        "max_days": SESSION_HISTORY_MAX_DAYS,
    }


class SessionsScreenStatSerializer(serializers.Serializer):
    """One of the dialog's "At a glance" numbers."""

    label = serializers.CharField()
    value = serializers.CharField()


class SessionsScreenSerializer(serializers.Serializer):
    """The activity sessions dialog."""

    days = HistoryScreenDaySerializer(many=True, help_text="Newest first, at most `max_days`.")
    stats = SessionsScreenStatSerializer(many=True)
    capped = serializers.BooleanField(help_text="More days exist than `max_days`.")
    max_days = serializers.IntegerField()
