"""Filtering and dedupe helpers for Discover rows."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING

from django.apps import apps

from app.models import (
    CollectionEntry,
    DiscoverFeedback,
    DiscoverFeedbackType,
    MediaTypes,
    Status,
)

if TYPE_CHECKING:
    from app.discover.schemas import CandidateItem

DEFAULT_BLOCKED_STATUSES = {
    Status.COMPLETED.value,
    Status.DROPPED.value,
    Status.IN_PROGRESS.value,
}

MEDIA_TYPE_TO_MODEL = {
    MediaTypes.MOVIE.value: "movie",
    MediaTypes.TV.value: "tv",
    MediaTypes.ANIME.value: "anime",
    MediaTypes.MUSIC.value: "music",
    MediaTypes.PODCAST.value: "podcast",
    MediaTypes.BOOK.value: "book",
    MediaTypes.COMIC.value: "comic",
    MediaTypes.MANGA.value: "manga",
    MediaTypes.GAME.value: "game",
    MediaTypes.BOARDGAME.value: "boardgame",
}

# Per-build memo for the library and feedback key sets. One Discover build asks
# for the same sets once per row; nothing changes them mid-build.
_build_memo: ContextVar[dict | None] = ContextVar("discover_build_memo", default=None)


@contextmanager
def memoized_key_lookups():
    """Reuse tracked and feedback key sets for the duration of one build."""
    token = _build_memo.set({}) if _build_memo.get() is None else None
    try:
        yield
    finally:
        if token is not None:
            _build_memo.reset(token)


def _memoized(key, compute):
    memo = _build_memo.get()
    if memo is None:
        return compute()
    if key not in memo:
        memo[key] = compute()
    # Callers extend the returned set, so each gets its own copy.
    return set(memo[key])


def get_tracked_keys_by_media_type(
    user,
    media_type: str,
    *,
    statuses: set[str] | None = None,
) -> set[tuple[str, str, str]]:
    """Return tracked keys for statuses excluded from most Discover rows."""
    target_statuses = frozenset(statuses or DEFAULT_BLOCKED_STATUSES)
    return _memoized(
        ("tracked", user.pk, media_type, target_statuses),
        lambda: _tracked_keys(user, media_type, target_statuses),
    )


def _tracked_keys(user, media_type, target_statuses):
    model_name = MEDIA_TYPE_TO_MODEL.get(media_type)
    if not model_name:
        return set()

    model = apps.get_model("app", model_name)
    rows = (
        model.objects.filter(user=user, status__in=target_statuses)
        .select_related("item")
        .only(
            "item__media_type",
            "item__source",
            "item__media_id",
            "status",
        )
    )

    return {
        (
            str(row.item.media_type),
            str(row.item.source),
            str(row.item.media_id),
        )
        for row in rows
        if row.item_id
    }


def get_feedback_keys_by_media_type(
    user,
    media_type: str,
    *,
    feedback_type: str = DiscoverFeedbackType.NOT_INTERESTED.value,
) -> set[tuple[str, str, str]]:
    """Return hidden Discover feedback identities for a media type."""
    return _memoized(
        ("feedback", user.pk, media_type, feedback_type),
        lambda: _feedback_keys(user, media_type, feedback_type),
    )


def _feedback_keys(user, media_type, feedback_type):
    rows = (
        DiscoverFeedback.objects.filter(
            user=user,
            item__media_type=media_type,
            feedback_type=feedback_type,
        )
        .select_related("item")
        .only(
            "item__media_type",
            "item__source",
            "item__media_id",
            "feedback_type",
        )
    )

    return {
        (
            str(row.item.media_type),
            str(row.item.source),
            str(row.item.media_id),
        )
        for row in rows
        if row.item_id
    }


def get_owned_keys_by_media_type(user, media_type: str) -> set[tuple[str, str, str]]:
    """Return identity keys for items already in the user's owned collection."""
    rows = (
        CollectionEntry.objects.filter(user=user, item__media_type=media_type)
        .select_related("item")
        .only("item__media_type", "item__source", "item__media_id")
    )

    return {
        (
            str(row.item.media_type),
            str(row.item.source),
            str(row.item.media_id),
        )
        for row in rows
        if row.item_id
    }


def exclude_owned_items(
    candidates: list[CandidateItem],
    owned_keys: set[tuple[str, str, str]],
) -> list[CandidateItem]:
    """Filter out candidates already present in the user's owned collection."""
    if not owned_keys:
        return list(candidates)
    return [
        candidate for candidate in candidates if candidate.identity() not in owned_keys
    ]


def exclude_tracked_items(
    candidates: list[CandidateItem],
    tracked_keys: set[tuple[str, str, str]],
) -> list[CandidateItem]:
    """Filter out candidates already tracked in excluded statuses."""
    if not tracked_keys:
        return list(candidates)
    return [
        candidate
        for candidate in candidates
        if candidate.identity() not in tracked_keys
    ]


def dedupe_candidates(
    candidates: list[CandidateItem],
    *,
    seen_identities: set[tuple[str, str, str]],
) -> list[CandidateItem]:
    """Dedupe candidates against already-rendered higher-priority rows."""
    unique_items: list[CandidateItem] = []
    for candidate in candidates:
        identity = candidate.identity()
        if identity in seen_identities:
            continue
        seen_identities.add(identity)
        unique_items.append(candidate)
    return unique_items
