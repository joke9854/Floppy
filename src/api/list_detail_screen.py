"""A list's page for the web (v2 P4-I2, smart lists P4-I3).

`GET /api/v1/lists/page/<reference>/` reads the Django list page's own
context (`build_list_detail_context`) for its `q`, `type`, `status`, `sort`,
`direction`, `layout` and `page`. Items go through the page's own table
adapter, so the Library's card and table builders draw them (cards in the
grid, cells in the table). A smart list reads its page's context too and
adds `smart`: the saved rules (every key, so the web posts them all back to
`list_smart_rules_update`), the rules summary, and the builder's options.
Lists the web does not draw (lists the user cannot edit, a missing list)
answer `handled: false` with the Django page to open.
"""

from __future__ import annotations

from django.http import HttpResponseBase
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from app.templatetags import app_tags

from .library_screen import (
    LibraryBulkSerializer,
    LibraryCardSerializer,
    LibraryColumnConfigSerializer,
    LibraryColumnSerializer,
    LibraryFilterOptionsSerializer,
    _bulk,
    _card,
    _column_config,
    _filter_options,
    _Table,
)

# The Django summary's words for the three-way rules (smart_rules_summary.html).
_THREE_WAY = {
    "rated": _("Rated"),
    "not_rated": _("Not Rated"),
    "collected": _("Collected"),
    "not_collected": _("Not Collected"),
    "released": _("Released"),
    "not_released": _("Not Released"),
}


def _smart_summary(rules: dict, status_labels: dict) -> list[dict]:
    """Return the saved rules as the Django page's summary chips (view mode)."""
    media_types = rules.get("media_types") or []
    chips = [
        {
            "label": _("Types:"),
            "value": ", ".join(str(app_tags.media_type_readable(value)) for value in media_types)
            if media_types
            else str(_("All Types")),
        },
    ]
    statuses = [value for value in rules.get("status") or [] if value != "all"]
    if statuses:
        chips.append(
            {
                "label": _("Status:"),
                "value": ", ".join(str(status_labels.get(value, value)) for value in statuses),
            },
        )
    for key, label in (("rating", _("Rating:")), ("collection", _("Collection:"))):
        value = rules.get(key)
        if value and value != "all":
            chips.append({"label": label, "value": str(_THREE_WAY.get(value, value))})
    for key, label in (("genre", _("Genre:")), ("implied_genre", _("Implied Genre:"))):
        if rules.get(key):
            chips.append({"label": label, "value": rules[key]})
    if rules.get("year"):
        year = rules["year"]
        chips.append({"label": _("Year:"), "value": str(_("Unknown")) if year == "unknown" else year})
    if rules.get("release") and rules["release"] != "all":
        chips.append({"label": _("Released:"), "value": str(_THREE_WAY.get(rules["release"], rules["release"]))})
    for key, label, upper in (
        ("source", _("Source:"), True),
        ("language", _("Language:"), True),
        ("country", _("Country:"), True),
        ("platform", _("Platform:"), False),
        ("origin", _("Origin:"), True),
    ):
        if rules.get(key):
            chips.append({"label": label, "value": rules[key].upper() if upper else rules[key]})
    if rules.get("search"):
        chips.append({"label": _("Search:"), "value": f"\u201c{rules['search']}\u201d"})
    return [{"label": str(chip["label"]), "value": str(chip["value"])} for chip in chips]


def _smart(context, custom_list) -> dict:
    """Return a smart list's rules, summary and builder options."""
    from lists import smart_rules

    rules = context["saved_smart_rules"]
    status_labels = {str(value): str(label) for value, label in context["status_choices"]}
    saved = {}
    for key, default in smart_rules.SMART_FILTER_DEFAULTS.items():
        value = rules.get(key, default)
        if key == "list":
            saved[key] = [int(entry) for entry in value or []]
        elif isinstance(default, list):
            saved[key] = [str(entry) for entry in value or []]
        else:
            saved[key] = "" if value is None else str(value)
    saved["media_types"] = [str(value) for value in rules.get("media_types") or []]
    filter_data = context.get("smart_filter_data") or {}
    return {
        "rules": saved,
        "summary": _smart_summary(rules, status_labels),
        "media_types": [
            {"value": value, "label": str(label)}
            for value, label in (context.get("available_media_type_labels") or {}).items()
        ],
        "granular_media_types": sorted(smart_rules.IMPLICIT_ALL_EXCLUDED_MEDIA_TYPES),
        "statuses": [
            {"value": str(value), "label": str(label)}
            for value, label in context["status_choices"]
            if value != "all"
        ],
        "filter_options": _filter_options({"filter_data": filter_data}),
        "lists": [
            {"value": str(row["id"]), "label": str(row["label"])}
            for row in filter_data.get("lists") or []
            if row["id"] != custom_list.id
        ],
        "save_url": reverse("list_smart_rules_update", args=[custom_list.id]),
    }


def _unhandled(url: str) -> dict:
    return {"handled": False, "django_url": url}


def build_list_detail_screen(request, reference: str) -> dict:
    """Return a manual list's page for the web, or where to open it instead."""
    from lists.views import build_list_detail_context
    from lists.views_helpers import (
        _adapt_list_items_for_table,
        _build_collection_platforms_by_item_id,
        _build_media_type_breakdown,
    )

    django_url = reverse("list_detail", args=[reference])
    context = build_list_detail_context(request, reference, smart_context=True)
    if isinstance(context, HttpResponseBase):
        return _unhandled(django_url)
    custom_list = context["custom_list"]
    if not context["can_edit"]:
        return _unhandled(django_url)
    is_smart = bool(custom_list.is_smart)
    breakdown = (
        _build_media_type_breakdown(custom_list)
        if is_smart
        else context.get("media_type_breakdown")
    )

    page = context["items"]
    layout = context["current_layout"]
    sort = context["current_sort"]
    if layout != "table":
        # The table adapts its rows already; the grid's go through the same
        # adapter so one card builder reads tracked and untracked items.
        platforms = _build_collection_platforms_by_item_id(
            request.user, [item.id for item in page.object_list]
        )
        _adapt_list_items_for_table(page, platforms)
    entries = list(page.object_list)
    media_type = context.get("table_column_media_type") or "all"
    table = _Table(request, {"current_sort": sort, "table_type": "list"}, entries, media_type) if layout == "table" else None

    public = custom_list.visibility == "public"
    links = []
    if public:
        json_url = reverse("list_json", args=[custom_list.public_reference])
        links = [
            {"label": _("RSS"), "href": reverse("list_rss", args=[custom_list.public_reference])},
            {"label": _("Radarr"), "href": f"{json_url}?arr=radarr"},
            {"label": _("Sonarr"), "href": f"{json_url}?arr=sonarr"},
        ]
    # A method on the model (templates call it implicitly).
    can_recommend = bool(custom_list.can_recommend())
    return {
        "handled": True,
        "django_url": django_url,
        "list": {
            "id": custom_list.id,
            "name": custom_list.name,
            "description": custom_list.description or "",
            "reference": custom_list.public_reference,
            "items_count": int(context["items_count"]),
            "filtered_count": int(context["filtered_items_count"]),
            "completion_percent": context.get("completion_percent"),
            "completed_count": int(context.get("completed_count") or 0),
            "collaborators_count": int(context["collaborators_count"]),
            "is_public": public,
            "links": links,
            "can_recommend": can_recommend,
            "recommendation_count": int(context.get("recommendation_count") or 0),
        },
        "breakdown": [
            {
                "value": str(row["value"]),
                "label": str(row["label"]),
                "count": int(row["count"]),
                "percent": int(row["percent"]),
                "color": str(row["color"]),
            }
            for row in breakdown or []
        ],
        "q": request.GET.get("q", ""),
        "sort": sort,
        "direction": context["current_direction"],
        "sorts": [{"value": value, "label": str(label)} for value, label in context["sort_choices"]],
        "statuses": []
        if is_smart
        else [{"value": str(value), "label": str(label)} for value, label in context["status_choices"]],
        "current_statuses": [] if is_smart else [str(value) for value in context["current_statuses"]],
        "media_types": [
            {"value": value, "label": str(app_tags.media_type_readable(value))}
            for value in context.get("media_types") or []
        ],
        "current_media_types": [] if is_smart else list(context["current_media_types"]),
        "layout": layout,
        "ordering": bool(context["list_ordering_enabled"]),
        "page": page.number,
        "has_next": page.has_next(),
        "columns": table.header() if table else [],
        "column_config": _column_config(context.get("column_config")),
        "default_column_config": _column_config(context.get("default_column_config")),
        "column_media_type": media_type,
        "cards": [_card(request, entry, sort, table) for entry in entries],
        "bulk": _bulk(context),
        "smart": _smart(context, custom_list) if is_smart else None,
        "urls": {
            "add_item": "" if is_smart else reverse("list_add_item", args=[custom_list.id]),
            "recommend": reverse("recommend_item", args=[custom_list.id]) if can_recommend else "",
            "recommendations": reverse("list_recommendations", args=[custom_list.id]),
            "activity": reverse("list_activity", args=[custom_list.id]),
            "export": reverse("list_export_csv", args=[custom_list.public_reference]),
            "reorder": reverse("list_reorder_item", args=[custom_list.id]),
            "columns": reverse("list_detail_columns", args=[custom_list.id]),
            "edit_form": reverse("list_edit_form", args=[custom_list.id]),
            "edit": reverse("list_edit"),
            "delete": reverse("list_delete"),
            "url_template": request.build_absolute_uri(reverse("list_detail", args=["__ref__"])),
        },
    }


class ListPageChoiceSerializer(serializers.Serializer):
    """A sort, status or media type option."""

    value = serializers.CharField()
    label = serializers.CharField()


class ListPageLinkSerializer(serializers.Serializer):
    """A Links menu entry (public lists)."""

    label = serializers.CharField()
    href = serializers.CharField()


class ListPageBreakdownSerializer(serializers.Serializer):
    """A slice of the media type breakdown."""

    value = serializers.CharField()
    label = serializers.CharField()
    count = serializers.IntegerField()
    percent = serializers.IntegerField()
    color = serializers.CharField()


class ListPageSummarySerializer(serializers.Serializer):
    """A smart rules summary chip."""

    label = serializers.CharField()
    value = serializers.CharField()


def _rules_fields() -> dict:
    from lists import smart_rules

    fields = {"media_types": serializers.ListField(child=serializers.CharField())}
    for key, default in smart_rules.SMART_FILTER_DEFAULTS.items():
        if key == "list":
            fields[key] = serializers.ListField(child=serializers.IntegerField())
        elif isinstance(default, list):
            fields[key] = serializers.ListField(child=serializers.CharField())
        else:
            fields[key] = serializers.CharField(allow_blank=True)
    return fields


ListPageSmartRulesSerializer = type(
    "ListPageSmartRulesSerializer",
    (serializers.Serializer,),
    {"__doc__": "Every saved smart rule (post them all back: one left out is cleared).", **_rules_fields()},
)


class ListPageSmartSerializer(serializers.Serializer):
    """A smart list's rules, summary and builder options."""

    rules = ListPageSmartRulesSerializer()
    summary = ListPageSummarySerializer(many=True)
    media_types = ListPageChoiceSerializer(many=True)
    granular_media_types = serializers.ListField(child=serializers.CharField())
    statuses = ListPageChoiceSerializer(many=True)
    filter_options = LibraryFilterOptionsSerializer()
    lists = ListPageChoiceSerializer(many=True)
    save_url = serializers.CharField()


class ListPageListSerializer(serializers.Serializer):
    """The list's header."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    reference = serializers.CharField()
    items_count = serializers.IntegerField()
    filtered_count = serializers.IntegerField()
    completion_percent = serializers.IntegerField(allow_null=True)
    completed_count = serializers.IntegerField()
    collaborators_count = serializers.IntegerField()
    is_public = serializers.BooleanField()
    links = ListPageLinkSerializer(many=True)
    can_recommend = serializers.BooleanField()
    recommendation_count = serializers.IntegerField()


class ListPageUrlsSerializer(serializers.Serializer):
    """The page's actions: Django pages, and where the web posts."""

    add_item = serializers.CharField(allow_blank=True)
    recommend = serializers.CharField(allow_blank=True)
    recommendations = serializers.CharField()
    activity = serializers.CharField()
    export = serializers.CharField()
    reorder = serializers.CharField()
    columns = serializers.CharField()
    edit_form = serializers.CharField()
    edit = serializers.CharField()
    delete = serializers.CharField()
    url_template = serializers.CharField()


class ListPageSerializer(serializers.Serializer):
    """A list's page for the web app (`handled: false`: open `django_url`)."""

    handled = serializers.BooleanField()
    django_url = serializers.CharField()
    list = ListPageListSerializer(required=False)
    breakdown = ListPageBreakdownSerializer(many=True, required=False)
    q = serializers.CharField(allow_blank=True, required=False)
    sort = serializers.CharField(required=False)
    direction = serializers.CharField(required=False)
    sorts = ListPageChoiceSerializer(many=True, required=False)
    statuses = ListPageChoiceSerializer(many=True, required=False)
    current_statuses = serializers.ListField(child=serializers.CharField(), required=False)
    media_types = ListPageChoiceSerializer(many=True, required=False)
    current_media_types = serializers.ListField(child=serializers.CharField(), required=False)
    layout = serializers.CharField(required=False)
    ordering = serializers.BooleanField(required=False)
    page = serializers.IntegerField(required=False)
    has_next = serializers.BooleanField(required=False)
    columns = LibraryColumnSerializer(many=True, required=False)
    column_config = LibraryColumnConfigSerializer(many=True, required=False)
    default_column_config = LibraryColumnConfigSerializer(many=True, required=False)
    column_media_type = serializers.CharField(required=False)
    cards = LibraryCardSerializer(many=True, required=False)
    bulk = LibraryBulkSerializer(allow_null=True, required=False)
    smart = ListPageSmartSerializer(allow_null=True, required=False)
    urls = ListPageUrlsSerializer(required=False)
