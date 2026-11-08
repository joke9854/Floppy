"""Optional fanart.tv artwork: a title's logo, poster and background.

Used only when a fanart.tv key is set in Settings > Metadata (or through
``FANART_API_KEY``). Movies are looked up by their TMDB id,
shows by their TVDB id (fanart.tv files TV under TVDB); the cache is keyed by
the page's own id. A lookup is cached for
7 days, an empty result too, so a title without art is not asked for again.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.db import transaction

from app.models import MediaTypes, Sources
from app.providers import credentials, services, tmdb

logger = logging.getLogger(__name__)

BASE_URL = "https://webservice.fanart.tv/v3"
CACHE_TTL = 60 * 60 * 24 * 7
# A failed lookup (not "no art") is retried after an hour.
ERROR_TTL = 60 * 60
# fanart.tv's art types per kind, best first.
ART_TYPES = {
    "movies": {
        "logo": ("hdmovielogo", "movielogo"),
        "poster": ("movieposter",),
        "background": ("moviebackground",),
    },
    "tv": {
        "logo": ("hdtvlogo", "clearlogo"),
        "poster": ("tvposter",),
        "background": ("showbackground",),
    },
}


def enabled() -> bool:
    """Return whether fanart.tv artwork is configured for the current user.

    Remembered on the request's user, since a grid asks once per card.
    """
    user = credentials._resolve_user(None)
    memo = getattr(user, "_fanart_enabled", None)
    if memo is None:
        memo = credentials.is_configured("fanart", user)
        if user is not None:
            user._fanart_enabled = memo
    return memo


# Seasons and episodes carry their show's media_id, and share its background
# and logo; a season keeps its own poster.
_SHOW_LEVEL_TYPES = (MediaTypes.SEASON.value, MediaTypes.EPISODE.value)


def _payload(item, slot) -> dict:
    """Return a movie or show lookup dict for a model or dict item."""

    def read(key):
        return item.get(key) if isinstance(item, dict) else getattr(item, key, None)

    media_type = read("media_type")
    if slot != "poster" and media_type in _SHOW_LEVEL_TYPES:
        media_type = MediaTypes.TV.value
    return {
        "source": read("source"),
        "media_type": media_type,
        "media_id": read("media_id"),
        "provider_external_ids": read("provider_external_ids") or {},
    }


def cached(item, slot) -> str | None:
    """Return a card's cached fanart.tv logo, poster or background, or None.

    Cache only, for grids and rows: a miss is fetched in the background so a
    later render has it.
    """
    if not item or not enabled():
        return None
    media = _payload(item, slot)
    art = artwork(media, allow_network=False)
    if art is None:
        _queue_fetch(media)
        return None
    return art.get(slot)


def _queue_fetch(media) -> None:
    """Fetch a title's art in a worker, once per title per hour."""
    lock_key = f"fanart_fetch_queued_{media['source']}_{media['media_type']}_{media['media_id']}"
    user = credentials._resolve_user(None)
    user_id = getattr(user, "pk", None)

    def enqueue():
        if not cache.add(lock_key, True, ERROR_TTL):
            return
        from app.tasks import fetch_fanart

        try:
            fetch_fanart.delay(media, user_id)
        except Exception:  # deliberate best-effort; provider art stays
            cache.delete(lock_key)

    transaction.on_commit(enqueue)


def _kind(media) -> str | None:
    """Return the fanart.tv kind a movie or show page's media is filed under."""
    source = media.get("source")
    media_type = media.get("media_type")
    if media_type == MediaTypes.MOVIE.value and source == Sources.TMDB.value:
        return "movies"
    if media_type in (MediaTypes.TV.value, MediaTypes.ANIME.value) and source in (
        Sources.TMDB.value,
        Sources.TVDB.value,
    ):
        return "tv"
    return None


def _fanart_id(kind, media) -> str | None:
    """Return the id fanart.tv files the title under: TMDB for movies, TVDB for TV.

    The detail shell's show payload carries no external ids, so a TMDB show's
    TVDB id is resolved here, on the fetch path only.
    """
    media_id = media.get("media_id")
    if kind == "movies" or media.get("source") == Sources.TVDB.value:
        return str(media_id)
    tvdb_id = (media.get("provider_external_ids") or {}).get("tvdb_id") or media.get("tvdb_id")
    if not tvdb_id:
        tvdb_id = tmdb.external_ids(MediaTypes.TV.value, media_id).get("tvdb_id")
    return str(tvdb_id) if tvdb_id else None


def _pick(images) -> str | None:
    """Return the best image URL: the site language, then English, then none."""
    if not images:
        return None
    language = (settings.TMDB_LANG or "en").split("-")[0]
    rank = {language: 0, "en": 1, "00": 2, "": 2}
    best = min(
        images,
        key=lambda image: (
            rank.get(image.get("lang") or "", 3),
            -int(image.get("likes") or 0),
        ),
    )
    return best.get("url") or None


def _parse(kind, data) -> dict:
    """Reduce a fanart.tv response to {logo, poster, background} URLs."""
    art = {}
    for slot, types in ART_TYPES[kind].items():
        for art_type in types:
            url = _pick(data.get(art_type))
            if url:
                art[slot] = url
                break
    return art


def artwork(media, *, allow_network=True) -> dict | None:
    """Return a title's fanart.tv {logo, poster, background}, or None.

    ``{}`` means fanart.tv has nothing for it (or is not configured, or the
    title has no id it files art under). ``None`` is a cache miss that
    ``allow_network=False`` left unfetched.
    """
    if not enabled() or not isinstance(media, dict):
        return {}
    kind = _kind(media)
    if kind is None:
        return {}
    # Keyed by the page's own id, so the shell reads it without a TVDB lookup.
    key = f"fanart_v2_{media.get('source')}_{kind}_{media.get('media_id')}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    if not allow_network:
        return None
    try:
        fanart_id = _fanart_id(kind, media)
        if fanart_id is None:
            cache.set(key, {}, CACHE_TTL)
            return {}
        data = services.api_request(
            "fanart",
            "GET",
            f"{BASE_URL}/{kind}/{fanart_id}",
            params={"api_key": credentials.get("fanart", "api_key")},
        )
    except services.ProviderAPIError as error:
        # fanart.tv answers 404 for a title it has no art for.
        not_found = error.status_code == requests.codes.not_found
        logger.info("fanart.tv lookup failed for %s", key)
        cache.set(key, {}, CACHE_TTL if not_found else ERROR_TTL)
        return {}
    except Exception:  # deliberate best-effort; provider art stays
        logger.info("fanart.tv lookup failed for %s", key)
        cache.set(key, {}, ERROR_TTL)
        return {}
    art = _parse(kind, data) if isinstance(data, dict) else {}
    cache.set(key, art, CACHE_TTL)
    return art
