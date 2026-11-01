from django.contrib import admin
from django.utils import timezone

from events.models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """Admin configuration for the Event model."""

    list_select_related = ["item"]
    search_fields = ["item__title", "item__media_id"]
    list_display = [
        "__str__",
        "formatted_datetime",
        "content_number",
        "notification_sent",
    ]
    list_filter = [
        "notification_sent",
        "item__media_type",
        "item__source",
        ("datetime", admin.DateFieldListFilter),
    ]

    def get_exclude(self, request, obj=None):
        """Hide exact unknown values from Django's timezone conversion widget."""
        exclude = super().get_exclude(request, obj)
        if obj is not None and (obj.is_unknown_released or obj.is_unknown_unreleased):
            return [*(exclude or []), "datetime"]
        return exclude

    def get_readonly_fields(self, request, obj=None):
        """Render exact unknown values through the semantic formatter."""
        readonly_fields = super().get_readonly_fields(request, obj)
        if obj is not None and (obj.is_unknown_released or obj.is_unknown_unreleased):
            return [*readonly_fields, "formatted_datetime"]
        return readonly_fields

    def formatted_datetime(self, obj):
        """Display datetime in a safe format, handling extreme values."""
        if obj.is_unknown_released:
            return "Unknown (released)"
        if obj.is_unknown_unreleased:
            return "Unknown (unreleased)"
        try:
            return timezone.localtime(obj.datetime).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, ValueError):
            return "Invalid date"
