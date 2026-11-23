"""The web Lists index (v2 P4-I1).

`GET /api/v1/lists/screen/` reads the Django Lists page's own context
(`build_lists_context`) for the page's `scope`, `q`, `media_type`, `sort`,
`direction` and `page`: the counts, the toolbar options, 20 cards a page with
their four-poster covers (the page's lazy list_cover_image, batched here),
and where the page's actions post. The list detail stays the Django page
until P4-I2.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import serializers

from app.templatetags import app_tags
from integrations.imports import trakt as trakt_imports
from lists.models import CustomListItem
from users.templatetags import user_tags

# The page shows its toolbar from this many lists.
TOOLBAR_FROM = 6


def _covers(list_ids) -> dict[int, list[str]]:
    """Return the first four posters of each list (date added), as the cover."""
    rows = (
        CustomListItem.objects.filter(custom_list_id__in=list_ids)
        .annotate(
            position=Window(
                RowNumber(),
                partition_by=[F("custom_list_id")],
                order_by=[F("date_added").asc(), F("pk").asc()],
            ),
        )
        .filter(position__lte=4)
        .select_related("item")
        .order_by("custom_list_id", "position")
    )
    covers: dict[int, list[str]] = {}
    for row in rows:
        image = app_tags.ct_poster(row.item) or settings.IMG_NONE
        url = app_tags.image_url(app_tags.tmdb_size(image, "w185"))
        covers.setdefault(row.custom_list_id, []).append(str(url or ""))
    return covers


def _card(custom_list, user, covers, sort) -> dict:
    shared = custom_list.owner_id != user.id or bool(list(custom_list.collaborators.all()))
    meta = [
        ngettext("%(value_1)s item", "%(value_1)s items", custom_list.items_count)
        % {"value_1": custom_list.items_count},
        _("Shared") if shared else _(custom_list.get_visibility_display()),
    ]
    if getattr(custom_list, "completion_percent", None):
        meta.append(_("%(value_1)s%% completed") % {"value_1": custom_list.completion_percent})
    watched = ""
    if sort == "last_watched":
        last = getattr(custom_list, "last_watched_at", None)
        watched = str(user_tags.user_date_format(last, user)) if last else _("No watched items")
    return {
        "id": custom_list.id,
        "name": custom_list.name,
        "href": reverse("list_detail", args=[custom_list.public_reference]),
        "meta": " · ".join(meta),
        "watched": watched,
        "is_smart": bool(custom_list.is_smart),
        "can_edit": bool(getattr(custom_list, "can_edit", False)),
        "covers": covers.get(custom_list.id, []),
    }


def build_lists_screen(request) -> dict:
    """Return the Lists index for the web from the page's context."""
    from lists.views_list_browse import build_lists_context

    context = build_lists_context(request)
    user = request.user
    page = context["custom_lists"]
    sort = context["current_sort"]
    covers = _covers([custom_list.id for custom_list in page])
    owned, shared = int(context["owned_count"]), int(context["shared_count"])
    query = context.get("search_query") or ""
    media_type = context["current_media_type"]
    return {
        "owned_count": owned,
        "shared_count": shared,
        "scope": context["current_scope"],
        "q": query,
        "media_type": media_type,
        "sort": sort,
        "direction": context["current_direction"],
        "sorts": [{"value": value, "label": str(label)} for value, label in context["sort_choices"]],
        "media_types": [
            {"value": "all", "label": _("All Types")},
            *[
                {"value": value, "label": str(app_tags.media_type_readable_plural(value))}
                for value in context["media_types"]
            ],
        ],
        # The page shows the toolbar from six lists, or while it filters.
        "show_toolbar": owned + shared > TOOLBAR_FROM or bool(query) or media_type != "all",
        "page": page.number,
        "has_next": page.has_next(),
        "cards": [_card(custom_list, user, covers, sort) for custom_list in page],
        "tag_options": list(context["available_tags"]),
        # The web connects Trakt with the device code flow (the imports API),
        # which needs this redirect URI in the user's Trakt application.
        "trakt_redirect_uri": trakt_imports.TRAKT_OOB_REDIRECT_URI,
        "urls": {
            "create": reverse("list_create"),
            "edit": reverse("list_edit"),
            "delete": reverse("list_delete"),
            "edit_form": reverse("list_edit_form", args=[0]).replace("/0/", "/{id}/"),
            "profile": reverse("user_profile", args=[user.username]),
            "url_template": request.build_absolute_uri(reverse("list_detail", args=["__ref__"])),
        },
    }


class ListsScreenChoiceSerializer(serializers.Serializer):
    """A sort or media type option."""

    value = serializers.CharField()
    label = serializers.CharField()


class ListsScreenCardSerializer(serializers.Serializer):
    """A list card: cover posters, name, "N items · Shared · N% completed"."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    href = serializers.CharField()
    meta = serializers.CharField()
    watched = serializers.CharField(allow_blank=True, help_text="Last watched, under that sort.")
    is_smart = serializers.BooleanField()
    can_edit = serializers.BooleanField()
    covers = serializers.ListField(child=serializers.CharField())


class ListsScreenUrlsSerializer(serializers.Serializer):
    """Where the page's actions post (`edit_form` has an `{id}` slot)."""

    create = serializers.CharField()
    edit = serializers.CharField()
    delete = serializers.CharField()
    edit_form = serializers.CharField()
    profile = serializers.CharField()
    url_template = serializers.CharField()


class ListsScreenSerializer(serializers.Serializer):
    """The Lists index for the web app."""

    owned_count = serializers.IntegerField()
    shared_count = serializers.IntegerField()
    scope = serializers.CharField()
    q = serializers.CharField(allow_blank=True)
    media_type = serializers.CharField()
    sort = serializers.CharField()
    direction = serializers.CharField()
    sorts = ListsScreenChoiceSerializer(many=True)
    media_types = ListsScreenChoiceSerializer(many=True)
    show_toolbar = serializers.BooleanField()
    page = serializers.IntegerField()
    has_next = serializers.BooleanField()
    cards = ListsScreenCardSerializer(many=True)
    tag_options = serializers.ListField(child=serializers.CharField())
    trakt_redirect_uri = serializers.CharField()
    urls = ListsScreenUrlsSerializer()
