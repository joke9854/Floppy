"""Fixed CineTrack Home sections (v2 Home, boards A1/A6).

Airing This Week, Recently Watched and the header's catch-up count. They sit
beside the user-configured rows, read only local data (calendar events and
watch history) and are cached per user with the Home rows, so the same writes
that clear a row (``clear_home_row_cache_for_user``) clear them too.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from app.cache_utils import (
    HOME_ROW_CACHE_PREFIX,
    HOME_ROW_CACHE_TTL,
    register_home_row_cache_key,
)
from app.models import Episode, Item, MediaTypes, Movie, Season, Status
from app.templatetags.app_tags import slug
from events.models import Event
from events.notifications import annotate_finale_events

AIRING_LIMIT = 6
RECENT_LIMIT = 12
# Episode rows scanned for Recently Watched: binges repeat a show, so the
# scan is wider than the shelf, but bounded.
RECENT_EPISODE_SCAN = 300


@dataclass
class AiringEntry:
    """One release in Airing This Week."""

    event: Event
    day: date
    is_today: bool
    tag: str | None  # "premiere", "finale" or None
    url: str | None = None  # the episode's page, when the release is one


def _airing_url(event: Event) -> str | None:
    """Return the released episode's detail URL, or None for other releases."""
    item = event.item
    if (
        item.media_type != MediaTypes.SEASON.value
        or item.season_number is None
        or event.content_number is None
    ):
        return None
    name = (
        "anime_episode_details"
        if item.library_media_type == MediaTypes.ANIME.value
        else "episode_details"
    )
    return reverse(
        name,
        kwargs={
            "source": item.source,
            "media_id": item.media_id,
            "title": slug(item.title) or "item",
            "season_number": item.season_number,
            "episode_number": event.content_number,
        },
    )


@dataclass
class RecentEntry:
    """One title in Recently Watched, as a poster card entry."""

    item: Item
    media: object
    watched_at: datetime
    subtitle_override: object = None
    show_progress_controls: bool = False


def _airing_this_week(user, today: date) -> tuple[list[AiringEntry], int]:
    """Return the next AIRING_LIMIT releases this week and the week's total."""
    queryset = Event.objects.get_user_events(user, today, today + timedelta(days=6))
    events = list(queryset[:AIRING_LIMIT])
    total = len(events) if len(events) < AIRING_LIMIT else queryset.count()
    entries = []
    # The notifications' rule: a season's highest known episode is its finale.
    for event in annotate_finale_events(events):
        tag = None
        if event.content_number == 1:
            tag = "premiere"
        elif event._is_season_finale:
            tag = "finale"
        day = timezone.localtime(event.datetime).date()
        entries.append(
            AiringEntry(event, day, day == today, tag, _airing_url(event)),
        )
    return entries, total


def _recently_watched(user) -> list[RecentEntry]:
    entries: dict[tuple[str, int], RecentEntry] = {}
    episodes = (
        Episode.objects.filter(related_season__user=user, end_date__isnull=False)
        .select_related("related_season__item", "related_season__related_tv__item")
        .order_by("-end_date")[:RECENT_EPISODE_SCAN]
    )
    for episode in episodes:
        season = episode.related_season
        media = season.related_tv or season
        key = ("tv", media.item_id)
        if key not in entries:
            entries[key] = RecentEntry(media.item, media, episode.end_date)
        if len(entries) >= RECENT_LIMIT:
            break
    movies = (
        Movie.objects.filter(user=user, end_date__isnull=False)
        .exclude(status=Status.PLANNING.value)
        .select_related("item")
        .order_by("-end_date")[:RECENT_LIMIT]
    )
    for movie in movies:
        entries.setdefault(
            ("movie", movie.item_id),
            RecentEntry(movie.item, movie, movie.end_date),
        )
    recent = sorted(entries.values(), key=lambda e: e.watched_at, reverse=True)
    for entry in recent[:RECENT_LIMIT]:
        entry.subtitle_override = timezone.localtime(entry.watched_at).date()
    return recent[:RECENT_LIMIT]


def _catch_up(user, now: datetime) -> tuple[int, int]:
    """Aired episodes not yet watched across in-progress seasons, and their shows."""
    seasons = {
        season_id: (item_id, tv_id)
        for season_id, item_id, tv_id in Season.objects.filter(
            user=user,
            status=Status.IN_PROGRESS.value,
        )
        .exclude(related_tv__status=Status.DROPPED.value)
        .values_list("id", "item_id", "related_tv_id")
    }
    if not seasons:
        return 0, 0
    aired = dict(
        Event.objects.filter(
            item_id__in=[item_id for item_id, _tv_id in seasons.values()],
            content_number__isnull=False,
            datetime__lte=now,
        )
        .values("item_id")
        .annotate(n=Count("content_number", distinct=True))
        .values_list("item_id", "n"),
    )
    watched = dict(
        Episode.objects.filter(related_season_id__in=seasons)
        .values("related_season_id")
        .annotate(n=Count("item__episode_number", distinct=True))
        .values_list("related_season_id", "n"),
    )
    episodes = 0
    shows = set()
    for season_id, (item_id, tv_id) in seasons.items():
        left = max(0, aired.get(item_id, 0) - watched.get(season_id, 0))
        if left:
            episodes += left
            shows.add(tv_id or f"season-{season_id}")
    return episodes, len(shows)


def build_home_sections(user) -> dict:
    """Return the v2 Home sections for a user, cached with the Home rows."""
    today = timezone.localdate()
    cache_key = f"{HOME_ROW_CACHE_PREFIX}_{user.id}_v2_sections_{today.isoformat()}"
    sections = cache.get(cache_key)
    if sections is None:
        airing, airing_count = _airing_this_week(user, today)
        catch_up, catch_up_shows = _catch_up(user, timezone.now())
        sections = {
            # Two columns of three on desktop (A1); phones show the first.
            "airing": [column for column in (airing[:3], airing[3:]) if column],
            "airing_count": airing_count,
            "recent": _recently_watched(user),
            "catch_up": catch_up,
            "catch_up_shows": catch_up_shows,
        }
        cache.set(cache_key, sections, HOME_ROW_CACHE_TTL)
        register_home_row_cache_key(user.id, cache_key)
    return sections

