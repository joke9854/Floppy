"""HTTP handlers for item-based bulk actions."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from app import bulk_actions, library_actions
from app.models import Status


def _missing_item_ids_response():
    return JsonResponse(
        {"success": False, "error": "At least one item is required."},
        status=400,
    )


@login_required
@require_POST
def bulk_status_update(request):
    """Update the selected user's item-backed media trackers."""
    item_ids = bulk_actions.posted_item_ids(request.POST)
    if not item_ids:
        return _missing_item_ids_response()

    status = request.POST.get("status", "")
    valid_statuses = {value for value, _label in Status.choices}
    if status not in valid_statuses:
        return JsonResponse(
            {"success": False, "error": "Invalid status."},
            status=400,
        )

    result = bulk_actions.apply_bulk_status(request.user, item_ids, status)
    result["success"] = True
    result["message"] = (
        f"Updated {result['updated'] + result['created']} item(s)."
        + (f" {result['created']} tracker(s) created." if result["created"] else "")
        + (f" {result['skipped']} skipped." if result["skipped"] else "")
    )
    return JsonResponse(result)


@login_required
@require_POST
def bulk_collection_quick_add(request):
    """Quick-add selected Items to the user's collection."""
    item_ids = bulk_actions.posted_item_ids(request.POST)
    if not item_ids:
        return _missing_item_ids_response()

    outcome = library_actions.add_items_to_collection(request.user, item_ids)
    result = {
        "created": outcome["created"],
        "already_present": outcome["already_present"],
        "skipped": len(outcome["skipped_ids"]),
    }

    result["success"] = True
    result["message"] = (
        f"Added {result['created']} item(s) to collection."
        + (f" {result['already_present']} already present." if result["already_present"] else "")
        + (f" {result['skipped']} skipped." if result["skipped"] else "")
    )
    return JsonResponse(result)
