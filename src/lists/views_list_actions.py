"""List management action views.

Covers CRUD, column preferences, the modal, item toggle and release-year fetch.

None of these views render the list detail page — they mutate state or return
small fragments. The read-heavy detail views live in views_list_detail.py and
views_smart_list.py; the browse views live in views_list_browse.py.
"""

import json
import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_not_required, login_required
from django.db import transaction
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext
from django.views.decorators.http import require_GET, require_POST

from app import helpers
from app.columns import sanitize_column_prefs
from app.discover import tab_cache as discover_tab_cache
from app.models import Item, MediaTypes
from app.providers import services
from app.services import metadata_resolution
from integrations.upload_staging import (
    enqueue_staged_task,
    stage_uploaded_file,
)
from lists import list_actions, smart_rules
from lists import tasks as list_tasks
from lists.forms import CustomListForm
from lists.models import (
    CustomList,
    CustomListItem,
    ListActivity,
    ListActivityType,
)
from lists.views_helpers import (
    _build_list_url_template,
    _list_item_title_fields_from_metadata,
    _maybe_backfill_episode_title,
)
from users.models import ListDetailSortChoices

logger = logging.getLogger(__name__)


@require_POST
def update_list_table_columns(request, list_id):
    """Persist list-table column prefs without overwriting regular media-list prefs."""
    if not request.user.is_authenticated:
        return HttpResponseBadRequest("Authentication required")

    custom_list = get_object_or_404(
        CustomList.objects.select_related("owner").prefetch_related("collaborators"),
        id=list_id,
    )
    if not custom_list.user_can_view(request.user):
        msg = "List not found"
        raise Http404(msg)

    media_type = request.POST.get("media_type_key", "all")
    if media_type != "all" and media_type not in MediaTypes.values:
        media_type = "all"

    raw_order = request.POST.get("order", "[]")
    raw_hidden = request.POST.get("hidden", "[]")

    try:
        parsed_order = json.loads(raw_order)
    except json.JSONDecodeError:
        parsed_order = []
    try:
        parsed_hidden = json.loads(raw_hidden)
    except json.JSONDecodeError:
        parsed_hidden = []

    order = (
        [value for value in parsed_order if isinstance(value, str)]
        if isinstance(parsed_order, list)
        else []
    )
    hidden = (
        [value for value in parsed_hidden if isinstance(value, str)]
        if isinstance(parsed_hidden, list)
        else []
    )

    valid_sorts = {choice[0] for choice in ListDetailSortChoices.choices}
    current_sort = request.POST.get("sort", ListDetailSortChoices.DATE_ADDED)
    if current_sort not in valid_sorts:
        current_sort = ListDetailSortChoices.DATE_ADDED

    clean_order, clean_hidden = sanitize_column_prefs(
        media_type=media_type,
        current_sort=current_sort,
        user=request.user,
        table_type="list",
        order=order,
        hidden=hidden,
    )

    request.user.update_column_prefs(
        media_type=media_type,
        table_type="list",
        order=clean_order,
        hidden=clean_hidden,
    )

    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps({"refreshTableColumns": True})
    return response


@require_POST
def create(request):
    """Create a new custom list."""
    data, unknown = _list_form_data(request)
    form = CustomListForm(data, user=request.user)
    if unknown:
        return _unknown_collaborators(unknown)
    if form.is_valid():
        custom_list = form.save(commit=False)
        custom_list.owner = request.user
        custom_list.save()
        form.save_m2m()
        logger.info("%s list created successfully.", custom_list)
        ListActivity.objects.create(
            custom_list=custom_list,
            user=request.user,
            activity_type=ListActivityType.LIST_CREATED,
        )
        if helpers.wants_json(request):
            return JsonResponse(_saved_list(custom_list, request))
        if custom_list.is_smart and request.POST.get("smart_create_flow"):
            return redirect(
                f"{reverse('list_detail', args=[custom_list.public_reference])}?edit_smart_rules=1",
            )
    else:
        logger.error(form.errors.as_json())
        if helpers.wants_json(request):
            return _form_errors(form)
        helpers.form_error_messages(form, request)
    return helpers.redirect_back(request)


@login_required
def _list_form_data(request):
    """Return the posted list form data, and any collaborator usernames not found.

    The web dialog (v2 P4-I) names collaborators by username
    (``collaborator_usernames``); the form takes user ids, so they are resolved
    here. The page's select2 posts ids, unchanged.
    """
    if "collaborator_usernames" not in request.POST:
        return request.POST, []
    names = [
        name.strip()
        for name in request.POST.getlist("collaborator_usernames")
        if name.strip()
    ]
    users = {
        user.username.casefold(): user
        for user in get_user_model().objects.filter(username__in=names)
    }
    for name in names:
        if name.casefold() not in users:
            match = get_user_model().objects.filter(username__iexact=name).first()
            if match:
                users[name.casefold()] = match
    unknown = [name for name in names if name.casefold() not in users]
    data = request.POST.copy()
    data.setlist(
        "collaborators",
        [str(users[name.casefold()].pk) for name in names if name.casefold() in users],
    )
    return data, unknown


def _unknown_collaborators(unknown):
    return JsonResponse(
        {
            "saved": False,
            "errors": {
                "collaborators": [
                    gettext("No user named %(names)s.") % {"names": ", ".join(unknown)},
                ],
            },
        },
        status=400,
    )


def _form_errors(form):
    return JsonResponse(
        {
            "saved": False,
            "errors": {
                field: [str(message) for message in messages_]
                for field, messages_ in form.errors.items()
            },
        },
        status=400,
    )


def _saved_list(custom_list, request):
    href = reverse("list_detail", args=[custom_list.public_reference])
    location = href
    if custom_list.is_smart and request.POST.get("smart_create_flow"):
        location = f"{href}?edit_smart_rules=1"
    return {
        "saved": True,
        "list": {"id": custom_list.id, "name": custom_list.name, "href": href},
        "location": location,
    }


def _list_form_values(custom_list, request):
    """Return every field of the edit form, as it would post them back."""
    return {
        "list_id": custom_list.id,
        "name": custom_list.name,
        "description": custom_list.description or "",
        "tags": CustomListForm._normalize_tags(custom_list.tags or []),
        "collaborators": [
            {"id": user.pk, "username": user.username}
            for user in custom_list.collaborators.order_by("username")
        ],
        "allow_recommendations": bool(custom_list.allow_recommendations),
        "is_smart": bool(custom_list.is_smart),
        "is_public": custom_list.visibility == "public",
        "include_notes": bool(custom_list.include_notes),
        "public_slug": custom_list.public_slug or "",
        "can_delete": custom_list.user_can_delete(request.user),
        "activity_url": reverse("list_activity", args=[custom_list.id]),
        "url_template": _build_list_url_template(request),
    }


@require_POST
def share_view(request):
    """Create (or reuse) a public smart list snapshotting the current view."""
    try:
        custom_list, _created = list_actions.share_view(
            request.user,
            request.POST.get("media_type", ""),
            request.POST,
        )
    except ValueError:
        return HttpResponseBadRequest("Invalid media type")
    return JsonResponse({"url": custom_list.get_absolute_url()})


@login_required
@require_POST
def smart_rules_update(request, list_id):
    """Persist smart list rules and sync list membership."""
    custom_list = get_object_or_404(CustomList, id=list_id)
    if not custom_list.user_can_edit(request.user):
        return HttpResponse(status=403)
    if not custom_list.is_smart:
        return JsonResponse({"error": "This list is not a smart list."}, status=400)

    payload = request.POST
    content_type = request.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    normalized = smart_rules.normalize_rule_payload(payload, custom_list.owner)
    custom_list.smart_media_types = normalized["media_types"]
    custom_list.smart_excluded_media_types = []
    custom_list.smart_filters = {
        key: normalized.get(key, smart_rules.SMART_FILTER_DEFAULTS[key])
        for key in smart_rules.SMART_FILTER_KEYS
    }
    custom_list.save(
        update_fields=[
            "smart_media_types",
            "smart_excluded_media_types",
            "smart_filters",
        ],
    )
    custom_list.sync_smart_items()

    return JsonResponse(
        {
            "items_count": custom_list.items.count(),
            "rules": normalized,
        },
    )


@require_POST
def edit(request):
    """Edit an existing custom list."""
    list_id = request.POST.get("list_id")
    custom_list = get_object_or_404(CustomList, id=list_id)
    if custom_list.user_can_edit(request.user):
        data, unknown = _list_form_data(request)
        if unknown:
            return _unknown_collaborators(unknown)
        form = CustomListForm(data, instance=custom_list, user=request.user)
        if form.is_valid():
            form.save()
            logger.info("%s list edited successfully.", custom_list)
            ListActivity.objects.create(
                custom_list=custom_list,
                user=request.user,
                activity_type=ListActivityType.LIST_EDITED,
            )
            if helpers.wants_json(request):
                return JsonResponse(_saved_list(custom_list, request))
        elif helpers.wants_json(request):
            # The page drops an invalid edit silently; the web shows why.
            return _form_errors(form)
    else:
        if helpers.wants_json(request):
            return JsonResponse(
                {"error": gettext("You do not have permission to edit this list.")},
                status=403,
            )
        messages.error(
            request, gettext("You do not have permission to edit this list.")
        )
    return helpers.redirect_back(request)


@require_GET
def edit_form(request, list_id):
    """Render the edit-list modal fragment for a single list, on demand.

    Building this select2-backed form for every list on the /lists page
    eagerly was expensive (a Redis round-trip per widget render), so it's
    fetched lazily when the user opens the edit modal instead.
    """
    custom_list = get_object_or_404(CustomList, id=list_id)
    if not custom_list.user_can_edit(request.user):
        return HttpResponse(status=403)
    if helpers.wants_json(request):
        return JsonResponse(_list_form_values(custom_list, request))

    available_tags = CustomListForm._normalize_tags(
        tag
        for other_list in CustomList.objects.filter(
            Q(owner=request.user) | Q(collaborators=request.user),
        ).only("tags")
        for tag in (other_list.tags or [])
    )
    form = CustomListForm(
        instance=custom_list,
        auto_id=f"id_{custom_list.id}_%s",
        user=request.user,
        available_tags=available_tags,
    )
    return render(
        request,
        "lists/components/list_form.html",
        {
            "form": form,
            "custom_list": custom_list,
            "list_url_template": _build_list_url_template(request),
        },
    )


@require_POST
def delete(request):
    """Delete a custom list."""
    list_id = request.POST.get("list_id")
    custom_list = get_object_or_404(CustomList, id=list_id)
    if custom_list.user_can_delete(request.user):
        custom_list.delete()
        logger.info("%s list deleted successfully.", custom_list)
        if helpers.wants_json(request):
            return JsonResponse({"deleted": True})
        return redirect("lists")

    if helpers.wants_json(request):
        return JsonResponse(
            {"error": gettext("You do not have permission to delete this list.")},
            status=403,
        )
    messages.error(request, gettext("You do not have permission to delete this list."))
    return helpers.redirect_back(request)


@require_POST
def import_list_csv(request):
    """Import a single custom list from an uploaded CSV file."""
    csv_file = request.FILES.get("csv_file")
    if not csv_file:
        messages.error(request, gettext("Select a CSV file to import."))
        return redirect("lists")

    try:
        staged_file = str(stage_uploaded_file(csv_file))
    except OSError:
        logger.exception("Could not stage custom list CSV upload")
        messages.error(
            request,
            "The upload could not be queued. Check available disk space and try again.",
        )
        return redirect("lists")

    try:
        enqueue_staged_task(
            list_tasks.import_list_csv_task,
            request.user.id,
            staged_file,
            "new",
            staged_paths=(staged_file,),
        )
    except Exception:
        logger.exception("Could not queue custom list CSV import")
        messages.error(request, "The list import could not be queued. Try again.")
        return redirect("lists")

    messages.info(request, gettext("List import started in the background."))
    return redirect("lists")


@require_GET
def lists_modal(
    request,
    source,
    media_type,
    media_id,
    season_number=None,
    episode_number=None,
):
    """Return the modal showing all custom lists and allowing to add to them."""
    tracking_media_type = metadata_resolution.get_tracking_media_type(
        media_type,
        source=source,
    )
    lookup = {
        "media_id": media_id,
        "source": source,
        "media_type": tracking_media_type,
        "season_number": season_number,
        "episode_number": episode_number,
    }
    if metadata_resolution.is_grouped_anime_route(media_type, source=source):
        lookup["library_media_type"] = MediaTypes.ANIME.value

    try:
        item = Item.objects.get(**lookup)
        _maybe_backfill_episode_title(item, force=True)
    except Item.MultipleObjectsReturned:
        item = Item.objects.filter(**lookup).first()
    except Item.DoesNotExist:
        metadata = services.get_media_metadata(
            media_type,
            media_id,
            source,
            [season_number],
            episode_number,
        )
        item = Item.objects.create(
            media_id=media_id,
            source=source,
            media_type=tracking_media_type,
            season_number=season_number,
            episode_number=episode_number,
            library_media_type=metadata.get("library_media_type") or media_type,
            image=metadata["image"],
            **_list_item_title_fields_from_metadata(tracking_media_type, metadata),
        )

    custom_lists = CustomList.objects.get_user_lists_with_item(request.user, item)
    if hasattr(custom_lists, "filter"):
        custom_lists = custom_lists.filter(is_smart=False)
    else:
        custom_lists = [
            custom_list
            for custom_list in custom_lists
            if not getattr(custom_list, "is_smart", False)
        ]
    custom_lists = list(custom_lists)
    on_list_count = sum(
        1 for custom_list in custom_lists if getattr(custom_list, "has_item", False)
    )

    selected_tag = (request.GET.get("tag") or "").strip()

    unique_tags = sorted(
        {
            tag.strip()
            for custom_list in custom_lists
            for tag in (custom_list.tags or [])
            if isinstance(tag, str) and tag.strip()
        },
        key=str.lower,
    )

    if selected_tag:
        selected_tag_folded = selected_tag.casefold()
        custom_lists = [
            custom_list
            for custom_list in custom_lists
            if any(
                isinstance(tag, str) and tag.strip().casefold() == selected_tag_folded
                for tag in (custom_list.tags or [])
            )
        ]

    if helpers.wants_json(request):
        return JsonResponse(
            {
                "item_id": item.id,
                "title": str(item.title or ""),
                "toggle_url": reverse("list_item_toggle"),
                "tags": unique_tags,
                "selected_tag": selected_tag,
                "on_list_count": on_list_count,
                "lists": [
                    {
                        "id": custom_list.id,
                        "name": str(custom_list.name),
                        "has_item": bool(getattr(custom_list, "has_item", False)),
                    }
                    for custom_list in custom_lists
                ],
            },
        )

    return render(
        request,
        "lists/components/fill_lists.html",
        {
            "item": item,
            "custom_lists": custom_lists,
            "list_tags": unique_tags,
            "selected_list_tag": selected_tag,
            "on_list_count": on_list_count,
        },
    )


def _list_item_toggle_error_response():
    """Return an empty HTMX response that only triggers an error toast.

    htmx doesn't swap the response body for 4xx/5xx status codes by
    default, so the button stays exactly as it was — accurate, since
    nothing committed — while HX-Trigger still fires the toast regardless
    of swap/status.
    """
    response = HttpResponse(status=500)
    response["HX-Trigger"] = json.dumps(
        {
            "showToast": {
                "message": (
                    "Couldn't update this list — please try again. If it "
                    "keeps happening, file a bug report from "
                    "Settings > Advanced."
                ),
                "type": "error",
            },
        },
    )
    return response


@require_POST
def list_item_toggle(request):
    """Add or remove an item from a custom list."""
    item_id = request.POST["item_id"]
    custom_list_id = request.POST["custom_list_id"]

    item = get_object_or_404(Item, id=item_id)
    discover_tab_cache.mark_active_from_request(
        request,
        fallback_media_type=item.media_type,
    )
    custom_list = get_object_or_404(
        CustomList.objects.filter(
            Q(owner=request.user) | Q(collaborators=request.user),
            id=custom_list_id,
        ).distinct(),  # To prevent duplicates, when user is owner and collaborator
    )

    if custom_list.is_smart:
        if helpers.wants_json(request):
            return JsonResponse({"error": "Smart lists fill themselves."}, status=403)
        return HttpResponse(status=403)

    try:
        with transaction.atomic():
            CustomListItem.objects.lock_custom_lists([custom_list.id])
            custom_list_item = CustomListItem.objects.filter(
                custom_list=custom_list,
                item=item,
            ).first()
            if custom_list_item is not None:
                # Instance-level delete renumbers the per-list sequence.
                custom_list_item.delete()
                has_item = False
                activity_type = ListActivityType.ITEM_REMOVED
                log_action = "removed from"
            else:
                CustomListItem.objects.create(
                    custom_list=custom_list,
                    item=item,
                    added_by=request.user,
                )
                has_item = True
                activity_type = ListActivityType.ITEM_ADDED
                log_action = "added to"

            ListActivity.objects.create(
                custom_list=custom_list,
                user=request.user,
                activity_type=activity_type,
                item=item,
            )
        logger.info("%s %s %s.", item, log_action, custom_list)
    except Exception:
        # Keep the last committed button state and surface every failed toggle.
        # The structured context contains database IDs only.
        logger.exception(
            "Failed to toggle list membership (item_id=%s, custom_list_id=%s, "
            "user_id=%s)",
            item.id,
            custom_list.id,
            request.user.id,
        )
        if helpers.wants_json(request):
            return JsonResponse(
                {"error": "Couldn't update this list. Please try again."},
                status=500,
            )
        return _list_item_toggle_error_response()

    if helpers.wants_json(request):
        return JsonResponse({"list_id": custom_list.id, "has_item": has_item})
    return render(
        request,
        "lists/components/list_item_button.html",
        {"custom_list": custom_list, "item": item, "has_item": has_item},
    )


@login_required
@require_POST
def bulk_list_add(request):
    """Add several items to one editable manual list."""
    from app.bulk_actions import posted_item_ids

    item_ids = posted_item_ids(request.POST)
    if not item_ids:
        return JsonResponse(
            {"success": False, "error": "At least one item is required."},
            status=400,
        )

    custom_list = get_object_or_404(
        CustomList.objects.filter(
            Q(owner=request.user) | Q(collaborators=request.user),
            id=request.POST.get("custom_list_id"),
        ).distinct(),
    )
    if custom_list.is_smart:
        return JsonResponse(
            {"success": False, "error": "Smart lists cannot be edited directly."},
            status=403,
        )

    result = list_actions.add_items_to_list(request.user, custom_list, item_ids)
    already_present = result.already_present
    skipped = result.skipped
    return JsonResponse(
        {
            "success": True,
            "added": result.added,
            "already_present": already_present,
            "skipped": skipped,
            "message": (
                f"Added {result.added} item(s) to {custom_list.name}."
                + (f" {already_present} already present." if already_present else "")
                + (f" {skipped} skipped." if skipped else "")
            ),
        },
    )


@require_GET
@login_not_required
def fetch_release_year(request):
    """Fetch release year for a single item asynchronously."""
    item_id = request.GET.get("item_id")
    if not item_id:
        return JsonResponse({"error": "item_id required"}, status=400)

    try:
        item = Item.objects.get(id=item_id)
    except Item.DoesNotExist:
        return JsonResponse({"error": "Item not found"}, status=404)

    if item.release_datetime:
        return JsonResponse({"year": item.release_datetime.year})

    if item.media_type == MediaTypes.SEASON.value and item.season_number:
        episode_release = (
            Item.objects.filter(
                media_id=item.media_id,
                source=item.source,
                media_type=MediaTypes.EPISODE.value,
                season_number=item.season_number,
                release_datetime__isnull=False,
            )
            .order_by("release_datetime")
            .values_list("release_datetime", flat=True)
            .first()
        )
        if episode_release:
            item.release_datetime = episode_release
            item.save(update_fields=["release_datetime"])
            return JsonResponse({"year": episode_release.year})

    try:
        season_numbers = None
        episode_number = None
        if item.media_type == MediaTypes.SEASON.value and item.season_number:
            season_numbers = [item.season_number]
        elif (
            item.media_type == MediaTypes.EPISODE.value
            and item.season_number is not None
            and item.episode_number is not None
        ):
            season_numbers = [item.season_number]
            episode_number = item.episode_number

        metadata = services.get_media_metadata(
            item.media_type,
            item.media_id,
            item.source,
            season_numbers=season_numbers,
            episode_number=episode_number,
        )
        if metadata:
            release_datetime = helpers.extract_release_datetime(metadata)
            if release_datetime:
                item.release_datetime = release_datetime
                item.save(update_fields=["release_datetime"])
                return JsonResponse({"year": release_datetime.year})
    except Exception as exc:
        logger.warning(
            "Failed to fetch release year for item %s: %s",
            item_id,
            exc,
        )

    return JsonResponse({"year": None})
