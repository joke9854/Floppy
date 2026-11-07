"""Horizontal (16:9) backdrop resolution shared by the web UI and the API.

Item.image holds a portrait poster (TMDB w500); backdrops are never stored on
the model, only fetched from the provider and cached in Redis for 7 days by
``lists.models.CustomList``.

``resolve_backdrop`` returns ``None`` when no backdrop exists, leaving the
choice of fallback to the caller: the web UI falls back to the poster so a
card always renders, while the API reports ``null`` so clients can pick their
own artwork.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from app.models import MediaTypes, Sources

# Episodes and seasons share their show's media_id, and TMDB files anime under
# /tv, so all three resolve against the show-level backdrop.
_SHOW_LEVEL_TYPES = (
    MediaTypes.EPISODE.value,
    MediaTypes.SEASON.value,
    MediaTypes.ANIME.value,
)
_TVDB_TYPES = (MediaTypes.TV.value, *_SHOW_LEVEL_TYPES)


def _read(item, key):
    """Read a field from either a serialized dict or a model instance."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def _identity(item):
    """Return (source, media_type, media_id) or None when incomplete."""
    if not item:
        return None
    source = _read(item, "source")
    media_type = _read(item, "media_type")
    media_id = _read(item, "media_id")
    if not source or not media_type or not media_id:
        return None
    return source, media_type, media_id


def _tvdb_tmdb_id(item):
    """Return the TMDB cross-reference the TVDB provider stores, if any."""
    return (_read(item, "provider_external_ids") or {}).get("tmdb_id")


def _usable(backdrop):
    """Treat the placeholder image as no backdrop at all."""
    if backdrop and backdrop != settings.IMG_NONE:
        return backdrop
    return None


def _cache_key(item) -> str | None:
    """Return the cache key a backdrop for this item lives under, if any."""
    identity = _identity(item)
    if identity is None:
        return None
    source, media_type, media_id = identity

    if source == Sources.TMDB.value:
        backdrop_media_type = (
            MediaTypes.TV.value if media_type in _SHOW_LEVEL_TYPES else media_type
        )
        if backdrop_media_type in (MediaTypes.MOVIE.value, MediaTypes.TV.value):
            return f"tmdb_backdrop_{backdrop_media_type}_{media_id}"

    if source == Sources.TVDB.value and media_type in _TVDB_TYPES:
        tmdb_id = _tvdb_tmdb_id(item)
        if tmdb_id:
            return f"tmdb_backdrop_tv_{tmdb_id}"

    if source == Sources.IGDB.value and media_type == MediaTypes.GAME.value:
        return f"igdb_backdrop_{media_id}"

    return None


def cached_backdrop(item) -> str | None:
    """Return an already-cached backdrop without triggering provider lookups."""
    key = _cache_key(item)
    return _usable(cache.get(key)) if key else None


def queue_backdrop_fetch(item) -> None:
    """Fetch an uncached backdrop in the background so the next render has it.

    Only a true miss is queued (a cached "no backdrop" is left alone), once per
    key per hour, after the request's transaction commits.
    """
    key = _cache_key(item)
    if not key or cache.get(key) is not None:
        return
    payload = {
        field: _read(item, field)
        for field in ("source", "media_type", "media_id", "provider_external_ids")
    }
    lock_key = f"backdrop_fetch_queued_{key}"

    def enqueue():
        if not cache.add(lock_key, True, 60 * 60):
            return
        from app.tasks import fetch_backdrop

        try:
            fetch_backdrop.delay(payload)
        except Exception:  # deliberate best-effort; the poster stays
            cache.delete(lock_key)

    transaction.on_commit(enqueue)


def resolve_backdrop(item, *, allow_network=True) -> str | None:
    """Return a horizontal backdrop URL for an item, or None if there is none.

    With ``allow_network=False`` only the Redis cache is consulted, so callers
    on a hot path never block on a provider request.
    """
    cached = cached_backdrop(item)
    if cached:
        return cached

    identity = _identity(item)
    if identity is None or not allow_network:
        return None
    source, media_type, media_id = identity

    try:
        from lists.models import CustomList
    except Exception:
        return None

    custom_list = CustomList()

    if source == Sources.TMDB.value and media_type in _SHOW_LEVEL_TYPES:
        return _fetch(custom_list._get_tmdb_backdrop, MediaTypes.TV.value, media_id)

    if source == Sources.TMDB.value and media_type in (
        MediaTypes.MOVIE.value,
        MediaTypes.TV.value,
    ):
        return _fetch(custom_list._get_tmdb_backdrop, media_type, media_id)

    if source == Sources.TVDB.value and media_type in _TVDB_TYPES:
        tmdb_id = _tvdb_tmdb_id(item)
        if tmdb_id:
            return _fetch(custom_list._get_tmdb_backdrop, MediaTypes.TV.value, tmdb_id)

    if source == Sources.IGDB.value and media_type == MediaTypes.GAME.value:
        return _fetch(custom_list._get_igdb_backdrop, media_id)

    return None


def _fetch(getter, *args) -> str | None:
    """Call a provider backdrop getter; artwork is never worth raising over."""
    try:
        return _usable(getter(*args))
    except Exception:  # deliberate best-effort; failure is non-fatal here
        return None
