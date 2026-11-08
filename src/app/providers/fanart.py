"""Optional fanart.tv artwork: a title's logo, poster and background.

Used only when ``FANART_API_KEY`` is set. Movies are looked up by their TMDB id,
shows by their TVDB id (fanart.tv files TV under TVDB). A lookup is cached for
7 days, an empty result too, so a title without art is not asked for again.
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache

from app.models import MediaTypes, Sources
from app.providers import services

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
    """Return whether fanart.tv artwork is configured."""
    return bool(settings.FANART_API_KEY)


def _lookup(media) -> tuple[str, str] | None:
    """Return (kind, fanart id) for a movie or show page's media, or None."""
    source = media.get("source")
    media_type = media.get("media_type")
    if media_type == MediaTypes.MOVIE.value and source == Sources.TMDB.value:
        return "movies", str(media.get("media_id"))
    if media_type not in (MediaTypes.TV.value, MediaTypes.ANIME.value):
        return None
    if source == Sources.TVDB.value:
        return "tv", str(media.get("media_id"))
    if source == Sources.TMDB.value:
        tvdb_id = (media.get("provider_external_ids") or {}).get("tvdb_id")
        return ("tv", str(tvdb_id)) if tvdb_id else None
    return None


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
    lookup = _lookup(media)
    if lookup is None:
        return {}
    kind, fanart_id = lookup
    key = f"fanart_v1_{kind}_{fanart_id}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    if not allow_network:
        return None
    try:
        data = services.api_request(
            "fanart",
            "GET",
            f"{BASE_URL}/{kind}/{fanart_id}",
            params={"api_key": settings.FANART_API_KEY},
        )
    except services.ProviderAPIError as error:
        # fanart.tv answers 404 for a title it has no art for.
        not_found = error.status_code == requests.codes.not_found
        logger.info("fanart.tv lookup failed for %s %s", kind, fanart_id)
        cache.set(key, {}, CACHE_TTL if not_found else ERROR_TTL)
        return {}
    except Exception:  # deliberate best-effort; provider art stays
        logger.info("fanart.tv lookup failed for %s %s", kind, fanart_id)
        cache.set(key, {}, ERROR_TTL)
        return {}
    art = _parse(kind, data) if isinstance(data, dict) else {}
    cache.set(key, art, CACHE_TTL)
    return art
