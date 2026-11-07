"""Media-details carousel (trailer + photos) resolution.

Distinct from ``backdrops.py``: that module returns a single horizontal image
(or ``None``) for card art, eagerly consulted on hot paths. This module
returns a multi-item {"video", "photos"} payload for the details page's
carousel, fetched lazily (only when the page's carousel fragment is
requested) and only for the media types/sources that actually expose a
trailer or photo gallery.
"""

from django.core.cache import cache

from app.models import MediaTypes, Sources
from app.providers import tmdb

_TMDB_CAROUSEL_TYPES = (MediaTypes.MOVIE.value, MediaTypes.TV.value, MediaTypes.SEASON.value)


def carousel_supported(media_type, source):
    """Return whether the given media_type/source combination can have a carousel."""
    if source == Sources.TMDB.value and media_type in _TMDB_CAROUSEL_TYPES:
        return True
    return bool(source == Sources.IGDB.value and media_type == MediaTypes.GAME.value)


def confirmed_empty(media_type, source, media_id, *, season_number=None) -> bool:
    """Return True if a prior fetch already confirmed there's no trailer/photos.

    Cache peek only (never fetches), so a page whose carousel was already
    found empty on an earlier view can render the plain, non-carousel layout
    up front instead of paying for the lazy carousel round trip again.
    """
    if source == Sources.TMDB.value and media_type in _TMDB_CAROUSEL_TYPES:
        data = tmdb.peek_carousel_media(media_type, media_id, season_number=season_number)
    elif source == Sources.IGDB.value and media_type == MediaTypes.GAME.value:
        data = cache.get(f"igdb_carousel_v2_{media_id}")
    else:
        return False
    return data is not None and not data["video"] and not data["photos"]


# A show's Trailers row reads at most this many of its newest seasons: each
# season is its own TMDB request the first time.
TRAILER_SEASON_LIMIT = 6


def resolve_trailers(media_type, source, media_id) -> list[dict]:
    """Return a TMDB movie's or show's trailers and teasers for the v2 Trailers row.

    A show lists its own videos, then each season's, newest season first,
    for its TRAILER_SEASON_LIMIT newest seasons. Each entry is
    {"key", "name", "type", "season"}; ``season`` is None for the title's own.
    """
    if source != Sources.TMDB.value or media_type not in (
        MediaTypes.MOVIE.value,
        MediaTypes.TV.value,
    ):
        return []
    sources = [(None, tmdb.carousel_media(media_type, media_id))]
    if media_type == MediaTypes.TV.value:
        seasons = (tmdb.tv(media_id).get("related") or {}).get("seasons") or []
        numbers = sorted(
            (s.get("season_number") for s in seasons if s.get("season_number")),
            reverse=True,
        )[:TRAILER_SEASON_LIMIT]
        sources += [
            (number, tmdb.carousel_media(MediaTypes.SEASON.value, media_id, season_number=number))
            for number in numbers
        ]
    trailers, seen = [], set()
    for season, data in sources:
        for video in data.get("videos") or []:
            # A season adds only real trailers and teasers, never the
            # any-video fallback the title itself gets.
            if season is not None and video.get("type") not in ("Trailer", "Teaser"):
                continue
            if video["key"] not in seen:
                seen.add(video["key"])
                trailers.append({**video, "season": season})
    return trailers


def resolve_carousel_media(media_type, source, media_id, *, season_number=None) -> dict | None:
    """Return {"video": {...}|None, "photos": [{"url", "thumb_url"}, ...]} or None."""
    if source == Sources.TMDB.value and media_type in _TMDB_CAROUSEL_TYPES:
        data = tmdb.carousel_media(media_type, media_id, season_number=season_number)
        photos = [
            {
                "url": tmdb.get_carousel_image_url(photo["file_path"], size="w1280"),
                "thumb_url": tmdb.get_carousel_image_url(photo["file_path"], size="w300"),
            }
            for photo in data["photos"]
        ]
        if not data["video"] and not photos:
            return None
        return {"video": data["video"], "photos": photos}

    if source == Sources.IGDB.value and media_type == MediaTypes.GAME.value:
        from lists.models import CustomList

        data = CustomList()._get_igdb_carousel_media(media_id)
        photos = [
            {
                # t_screenshot_big_2x and similar named IGDB transforms crop to a
                # fixed canvas; t_1080p only caps resolution, so it keeps the
                # source image's real aspect ratio for the main pane/lightbox.
                "url": f"https://images.igdb.com/igdb/image/upload/t_1080p/{image_id}.jpg",
                "thumb_url": (
                    f"https://images.igdb.com/igdb/image/upload/"
                    f"t_screenshot_big_2x/{image_id}.jpg"
                ),
            }
            for image_id in data["photos"]
        ]
        if not data["video"] and not photos:
            return None
        return {"video": data["video"], "photos": photos}

    return None
