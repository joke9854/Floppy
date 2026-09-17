"""Provider metadata cache helpers and item metadata fetch utilities.

Extracted from tasks.py. Re-exported from app.tasks for backward compatibility.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from app import metadata_utils
from app.log_safety import exception_summary
from app.models import Item, MediaTypes, Sources
from app.providers import services
from app.services import metadata_resolution
from app.services.metadata_sync import enrich_synced_item
from app.tasks_backfill_state import MalformedItemIdentityError

logger = logging.getLogger(__name__)
CINETRACK_HYDRATION_LOCK_TTL = 15 * 60


def _exception_with_details(exc: Exception) -> str:
    """Return a compact exception summary that preserves the message when present."""
    summary = exception_summary(exc)
    details = str(exc).strip()
    if details and details != summary:
        return f"{summary}: {details}"
    return summary


def _metadata_cache_keys_for_item(item: Item):
    keys = {
        f"{item.source}_{item.media_type}_{item.media_id}",
    }
    if item.source == Sources.TVDB.value:
        from app.providers import tvdb

        keys.update(
            tvdb.metadata_cache_keys(
                item.media_id,
                item.season_number
                if item.media_type == MediaTypes.SEASON.value
                else None,
            ),
        )
    if item.source == Sources.TMDB.value:
        from app.providers import tmdb

        # Built through the provider's own helpers because the movie and season
        # keys carry a strategy version the hand-rolled key above doesn't have,
        # so clearing by that shape alone would silently miss them (issue #1066).
        keys.update(
            tmdb.metadata_cache_keys(
                item.media_id,
                item.media_type,
                season_number=item.season_number,
                episode_number=item.episode_number,
            ),
        )
    if (
        item.source == Sources.BGG.value
        and item.media_type == MediaTypes.BOARDGAME.value
    ):
        keys.add(f"bgg_metadata_{item.media_id}")
    if (
        item.source == Sources.MUSICBRAINZ.value
        and item.media_type == MediaTypes.MUSIC.value
    ):
        keys.add(f"musicbrainz_recording_{item.media_id}")
    return [key for key in keys if key]


def _clear_item_metadata_cache(item: Item):
    keys = _metadata_cache_keys_for_item(item)
    if not keys:
        return
    try:
        cache.delete_many(keys)
    except Exception:  # pragma: no cover - cache backends may not support delete_many
        for key in keys:
            try:
                cache.delete(key)
            except Exception:  # noqa: S112  # deliberate best-effort; skip the item and continue
                continue


def _fetch_item_metadata(item: Item):
    if item.media_type == MediaTypes.SEASON.value:
        if item.season_number is None:
            msg = "season item missing season_number"
            raise MalformedItemIdentityError(msg)
        return services.get_media_metadata(
            item.media_type,
            item.media_id,
            item.source,
            [item.season_number],
        )
    if item.media_type == MediaTypes.EPISODE.value:
        if item.season_number is None or item.episode_number is None:
            msg = "episode item missing season_number or episode_number"
            raise MalformedItemIdentityError(msg)
        return services.get_media_metadata(
            item.media_type,
            item.media_id,
            item.source,
            [item.season_number],
            item.episode_number,
        )
    return services.get_media_metadata(
        item.media_type,
        item.media_id,
        item.source,
    )


def _cinetrack_hydration_lock_key(item_id):
    return f"cinetrack:bootstrap:metadata-hydration:{int(item_id)}"


def queue_cinetrack_bootstrap_hydration(item_ids, user_id):
    """Queue metadata enrichment after commit, deduplicated per persisted Item.

    Initial CineTrack bootstrap intentionally persists tracking facts without
    waiting for provider metadata.  This helper restores rich metadata in the
    background without letting a retry enqueue the same item repeatedly.
    """
    normalized_ids = sorted({int(item_id) for item_id in item_ids if item_id})
    if not normalized_ids:
        return

    def enqueue_after_commit():
        selected = []
        for item_id in normalized_ids:
            if cache.add(
                _cinetrack_hydration_lock_key(item_id),
                "queued",
                timeout=CINETRACK_HYDRATION_LOCK_TTL,
            ):
                selected.append(item_id)
        if not selected:
            return
        try:
            hydrate_cinetrack_bootstrap_items.apply_async(
                args=[selected, int(user_id)],
                priority=getattr(settings, "CELERY_TASK_PRIORITY_BACKGROUND", 9),
            )
        except Exception:
            cache.delete_many(
                [_cinetrack_hydration_lock_key(item_id) for item_id in selected],
            )
            logger.exception(
                "cinetrack_bootstrap_metadata_hydration_enqueue_failed item_count=%s",
                len(selected),
            )

    transaction.on_commit(enqueue_after_commit)


@shared_task(name="Hydrate CineTrack bootstrap metadata", ignore_result=True)
def hydrate_cinetrack_bootstrap_items(item_ids, user_id):
    """Enrich minimal CineTrack bootstrap Items away from the request path."""
    normalized_ids = sorted({int(item_id) for item_id in item_ids if item_id})
    if not normalized_ids:
        return {"processed": 0, "failed": 0}

    user = get_user_model().objects.filter(pk=user_id).first()
    if user is None:
        cache.delete_many(
            [_cinetrack_hydration_lock_key(item_id) for item_id in normalized_ids],
        )
        return {"processed": 0, "failed": len(normalized_ids)}

    items = {
        item.id: item
        for item in Item.objects.filter(
            id__in=normalized_ids,
            media_type__in=(MediaTypes.MOVIE.value, MediaTypes.TV.value),
        )
    }
    processed = 0
    failed = 0
    language = metadata_resolution.metadata_language_default(user)

    for item_id in normalized_ids:
        lock_key = _cinetrack_hydration_lock_key(item_id)
        item = items.get(item_id)
        if item is None or item.source == Sources.MANUAL.value:
            cache.delete(lock_key)
            continue
        try:
            metadata = services.get_media_metadata(
                item.media_type,
                item.media_id,
                item.source,
                language=language,
            )
            item_fields = Item.title_fields_from_metadata(metadata)
            if metadata.get("image"):
                item_fields["image"] = metadata["image"]
            if item_fields:
                Item.objects.filter(pk=item.pk).update(**item_fields)
                for field_name, value in item_fields.items():
                    setattr(item, field_name, value)

            warnings, _preferred_provider = enrich_synced_item(
                item,
                metadata,
                source=item.source,
                route_media_type=item.media_type,
                tracking_media_type=item.media_type,
                season_number=None,
                user=user,
            )
            for warning in warnings:
                logger.warning(
                    "cinetrack_bootstrap_metadata_hydration_partial item_id=%s warning=%s",
                    item.id,
                    warning,
                )
            if item.metadata_fetched_at is None:
                Item.objects.filter(pk=item.pk).update(metadata_fetched_at=timezone.now())
            item.fetch_releases(delay=True)
            processed += 1
        except Exception as error:
            failed += 1
            logger.warning(
                "cinetrack_bootstrap_metadata_hydration_failed item_id=%s error=%s",
                item_id,
                exception_summary(error),
            )
        finally:
            cache.delete(lock_key)

    return {"processed": processed, "failed": failed}
