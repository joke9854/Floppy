"""Public poster wall for the sign-in page (A15).

The sign-in page is visible before authentication, so it may only show public
data: TMDB's trending movies and shows. The page never calls TMDB itself. It
reads a cached list and, on a miss, schedules one background refresh; until
that lands the wall keeps its placeholder tiles.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from app.models import MediaTypes

logger = logging.getLogger(__name__)

CACHE_KEY = "login_wall_posters:v1"
LOCK_KEY = "login_wall_posters:refreshing"
POSTERS_TTL = 60 * 60 * 24
EMPTY_TTL = 60 * 60
LOCK_TTL = 60 * 10
MAX_POSTERS = 36


def cached_posters():
    """Return cached poster URLs, scheduling a refresh when there are none."""
    posters = cache.get(CACHE_KEY)
    if posters is None:
        if cache.add(LOCK_KEY, True, LOCK_TTL):
            from app.tasks import refresh_login_wall_posters

            try:
                refresh_login_wall_posters.delay()
            except Exception:  # A broker outage must not break sign-in.
                cache.delete(LOCK_KEY)
                logger.warning("login_wall_refresh_schedule_failed", exc_info=True)
        return []
    return posters


def refresh_posters():
    """Fetch trending posters from TMDB and cache their URLs."""
    from app.discover.providers.tmdb_adapter import TMDbDiscoverAdapter

    adapter = TMDbDiscoverAdapter()
    posters = []
    for media_type in (MediaTypes.MOVIE.value, MediaTypes.TV.value):
        for candidate in adapter.trending(media_type, limit=MAX_POSTERS):
            image = candidate.image
            if image and image != settings.IMG_NONE and image not in posters:
                # w342 is plenty for 150px tiles and a third of w500's weight.
                posters.append(image.replace("/t/p/w500/", "/t/p/w342/"))
    posters = posters[:MAX_POSTERS]
    cache.set(CACHE_KEY, posters, POSTERS_TTL if posters else EMPTY_TTL)
    cache.delete(LOCK_KEY)
    return posters
