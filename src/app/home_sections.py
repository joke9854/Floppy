"""Fixed CineTrack Home sections (v2 Home).

In Progress, Airing This Week, Recently Watched and Coming Soon, in that order.
They read only local data (watch history and calendar events), are cached per
user per day with the Home cache keys, and are cleared by the same writes
(``clear_home_row_cache_for_user``).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

from django.apps import apps
from django.core.cache import cache
from django.db.models import Count, Max, Q
from django.urls import reverse
from django.utils import timezone

from app.activity_builders import _annotate_home_card_images
from app.cache_utils import (
    HOME_ROW_CACHE_PREFIX,
    HOME_ROW_CACHE_TTL,
    register_home_row_cache_key,
)
from app.models import (
    TV,
    Anime,
    BasicMedia,
    Episode,
    Item,
    MediaTypes,
    Movie,
    PlaybackProgress,
    Season,
    Sources,
    Status,
)
from app.models.manager import released_episode_breakdowns
from app.services.item_merge import dedupe_cross_provider_items
from app.templatetags.app_tags import slug
from events.models import Event
from events.notifications import annotate_finale_events

IN_PROGRESS_SHOW_STATUSES = (
    Status.IN_PROGRESS.value,
    Status.PLANNING.value,
    Status.COMPLETED.value,
)
IN_PROGRESS_MOVIE_STATUSES = (Status.IN_PROGRESS.value, Status.PLANNING.value)
IN_PROGRESS_LIMIT = 20
# A movie resumes after the first two minutes and before its last 5%: earlier is
# a false start, later is as good as finished.
MOVIE_RESUME_MIN_SECONDS = 120
MOVIE_RESUME_MAX_FRACTION = 0.95
AIRING_LIMIT = 6
COMING_SOON_DAYS = 90
COMING_SOON_LIMIT = 12
RECENT_LIMIT = 12
# Episode rows scanned for Recently Watched: binges repeat a show, so the
# scan is wider than the shelf, but bounded.
RECENT_EPISODE_SCAN = 300
HOME_CARD_UNREAD_ITEM_FIELDS = ("watch_providers",)


@dataclass
class HomeRowEntry:
    """One Home card: a tracked (or untracked) item and its media record."""

    item: Item
    media: object | None = None
    use_podcast_show: bool = False
    podcast_show: object | None = None
    show_progress_controls: bool = True
    subtitle_override: object | None = None
    # Movies in In Progress: the resume position as a percentage of the runtime.
    resume_percent: int | None = None


class _PartWatched(NamedTuple):
    """A show's latest part-watched episode, as the In Progress row reads it."""

    updated_at: datetime
    item_id: int
    season_number: int | None
    episode_number: int | None
    position_seconds: int
    duration_seconds: int | None


@dataclass
class ContinueEntry(HomeRowEntry):
    """An In Progress card: the Home card plus the episode it points at and its progress."""

    # Shows: the episode the card names (its part-watched episode, else the next one).
    target_item_id: int | None = None
    target_season_number: int | None = None
    target_episode_number: int | None = None
    target_title: str | None = None
    position_seconds: int | None = None
    duration_seconds: int | None = None
    # Duration minus position, when the runtime is known.
    remaining_seconds: int | None = None
    watched_count: int | None = None
    released_count: int | None = None
    is_rewatch: bool = False
    last_activity: datetime | None = None

    @property
    def kind(self) -> str:
        """Return "movie" or "show", the row's type filter."""
        return "movie" if self.item.media_type == MediaTypes.MOVIE.value else "show"

    def check_target(self) -> dict | None:
        """Return the episode the card's check marks watched, in episode_save's fields."""
        if self.target_season_number is None or self.target_episode_number is None:
            return None
        return {
            "media_id": self.item.media_id,
            "source": self.item.source,
            "season_number": self.target_season_number,
            "episode_number": self.target_episode_number,
            "library_media_type": self.item.library_media_type,
            "episode_title": self.target_title,
        }


@dataclass
class AiringEntry:
    """One release in Airing This Week or Coming Soon."""

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


def _airing_entries(events: list[Event], today: date) -> list[AiringEntry]:
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
    return entries


def _airing_this_week(user, today: date) -> tuple[list[AiringEntry], int]:
    """Return the next AIRING_LIMIT releases this week and the week's total."""
    queryset = Event.objects.get_user_events(user, today, today + timedelta(days=6))
    events = list(queryset[:AIRING_LIMIT])
    total = len(events) if len(events) < AIRING_LIMIT else queryset.count()
    return _airing_entries(events, today), total


def _title_key(media_type: str, media_id: str, item_id: int) -> tuple:
    """Return the key that makes a show one title (its seasons share it)."""
    if media_type == MediaTypes.SEASON.value:
        return ("show", media_id)
    return ("item", item_id)


def _coming_soon(user, today: date) -> list[AiringEntry]:
    """Upcoming releases after this week, soonest first, one per title.

    A title that airs this week is left out, so it never shows in both.
    """
    week = Event.objects.get_user_events(user, today, today + timedelta(days=6))
    airing_keys = {
        _title_key(media_type, media_id, item_id)
        for media_type, media_id, item_id in week.values_list(
            "item__media_type",
            "item__media_id",
            "item_id",
        )
    }
    upcoming = Event.objects.get_user_events(
        user,
        today + timedelta(days=7),
        today + timedelta(days=COMING_SOON_DAYS),
    )
    seen = set()
    events = []
    for event in upcoming:
        key = _title_key(event.item.media_type, event.item.media_id, event.item_id)
        if key in airing_keys or key in seen:
            continue
        seen.add(key)
        events.append(event)
        if len(events) >= COMING_SOON_LIMIT:
            break
    return _airing_entries(events, today)


def build_continue_watching(user) -> list[ContinueEntry]:
    """Return the In Progress row: shows and movies with real progress, latest first.

    A show needs a watched episode and a released episode still unwatched, or
    a part-watched episode. A Planning show qualifies only through a
    part-watched episode; a Completed show only through a newer released
    episode. A show in an open rewatch pass qualifies while its rewatch still
    has a next episode. A flat anime (tracked by count, no episodes) needs
    progress above zero and below its released episodes; Planning never
    qualifies. A movie needs a resume position between MOVIE_RESUME_MIN_SECONDS
    and MOVIE_RESUME_MAX_FRACTION of its runtime; a Completed movie with one is a
    rewatch. Paused and Dropped titles never show. Reads local data only: no
    provider calls.
    """
    now = timezone.now()
    earliest = datetime.min.replace(tzinfo=UTC)

    # Keys are (media_id, source), the order released_episode_breakdowns uses.
    shows: dict[tuple[str, str], tuple[int, str]] = {}
    for model in (TV, Anime):
        for item_id, media_id, source, status in model.objects.filter(
            user=user,
            status__in=IN_PROGRESS_SHOW_STATUSES,
            item__media_type=MediaTypes.TV.value,
        ).values_list("item_id", "item__media_id", "item__source", "status"):
            shows[(media_id, source)] = (item_id, status)
    media_ids = {media_id for media_id, _source in shows}

    watched: dict[tuple[str, str], dict[int, set[int]]] = defaultdict(
        lambda: defaultdict(set)
    )
    activity: dict[tuple[str, str], datetime] = {}
    part_target: dict[tuple[str, str], _PartWatched] = {}
    rewatching: set[tuple[str, str]] = set()
    released: dict[tuple[str, str], dict[int, int]] = {}
    if shows:
        episode_rows = (
            Episode.objects.filter(
                related_season__user=user,
                related_season__item__media_id__in=media_ids,
                item__episode_number__isnull=False,
            )
            .exclude(related_season__item__season_number=0)
            .order_by()
            .values(
                "related_season__item__media_id",
                "related_season__item__source",
                "related_season__item__season_number",
                "item__episode_number",
            )
            .annotate(last_end=Max("end_date"))
        )
        for row in episode_rows:
            key = (
                row["related_season__item__media_id"],
                row["related_season__item__source"],
            )
            watched[key][row["related_season__item__season_number"]].add(
                row["item__episode_number"]
            )
            if row["last_end"] is not None:
                activity[key] = max(activity.get(key, earliest), row["last_end"])

        tracked: dict[tuple[str, str], set[int]] = defaultdict(set)
        for media_id, source, season_number, rewatch_started_at, season_status in (
            Season.objects.filter(user=user, item__media_id__in=media_ids)
            .order_by()
            .values_list(
                "item__media_id",
                "item__source",
                "item__season_number",
                "rewatch_started_at",
                "status",
            )
        ):
            tracked[(media_id, source)].add(season_number)
            # TV.is_rewatching's rule: an open pass on a season that is not Dropped.
            if rewatch_started_at is not None and season_status != Status.DROPPED.value:
                rewatching.add((media_id, source))
        released = released_episode_breakdowns(shows, now, tracked)

        part_rows = (
            PlaybackProgress.objects.filter(
                user=user,
                completed=False,
                position_seconds__gt=0,
                item__media_type=MediaTypes.EPISODE.value,
                item__media_id__in=media_ids,
            )
            .order_by()
            .values_list(
                "item__media_id",
                "item__source",
                "updated_at",
                "item_id",
                "item__season_number",
                "item__episode_number",
                "position_seconds",
                "duration_seconds",
            )
        )
        part_rows = list(part_rows)
        # A position older than a recorded watch of that episode is stale: the
        # player never sent completed=True, but the episode has been marked watched.
        last_watched = dict(
            Episode.objects.filter(
                related_season__user=user,
                item_id__in={row[3] for row in part_rows},
                end_date__isnull=False,
            )
            .values("item_id")
            .annotate(last=Max("end_date"))
            .values_list("item_id", "last")
        ) if part_rows else {}
        for media_id, source, *fields in part_rows:
            key = (media_id, source)
            part = _PartWatched(*fields)
            watched_at = last_watched.get(part.item_id)
            if watched_at is not None and watched_at >= part.updated_at:
                continue
            if key not in part_target or part.updated_at > part_target[key].updated_at:
                part_target[key] = part

    candidates: dict[int, datetime] = {}
    show_counts: dict[int, tuple[int, int]] = {}
    rewatch_only: set[int] = set()
    for key, (item_id, status) in shows.items():
        played = watched.get(key, {})
        released_total = sum(released.get(key, {}).values())
        # Released episodes with no watch yet, season by season; episodes count from 1.
        unwatched = sum(
            count - sum(1 for number in played.get(season, ()) if number <= count)
            for season, count in released.get(key, {}).items()
        )
        partial = key in part_target
        if status == Status.PLANNING.value:
            qualifies = partial
        elif status == Status.COMPLETED.value:
            qualifies = unwatched > 0
        else:
            qualifies = partial or (bool(played) and unwatched > 0)
        # An open rewatch keeps its show in the row even when every released episode
        # already has a play; the target check later drops it once the pass is done.
        in_rewatch = key in rewatching and not qualifies
        if qualifies or in_rewatch:
            if in_rewatch:
                rewatch_only.add(item_id)
            part = part_target.get(key)
            candidates[item_id] = max(
                (
                    stamp
                    for stamp in (activity.get(key), part.updated_at if part else None)
                    if stamp
                ),
                default=earliest,
            )
            show_counts[item_id] = (released_total - unwatched, released_total)

    flat_anime = list(
        Anime.objects.filter(
            user=user,
            status__in=(Status.IN_PROGRESS.value, Status.COMPLETED.value),
            item__media_type=MediaTypes.ANIME.value,
            progress__gt=0,
        ).select_related("item")
    )
    if flat_anime:
        # The events-derived released count; no provider call on Home.
        BasicMedia.objects.annotate_max_progress(
            flat_anime, MediaTypes.ANIME.value, cached_only=True
        )
        for record in flat_anime:
            if record.max_progress and record.progress < record.max_progress:
                candidates[record.item_id] = earliest

    resume: dict[int, tuple[int, int | None]] = {}
    resume_at: dict[int, datetime] = {}
    for item_id, position, duration, updated_at in (
        PlaybackProgress.objects.filter(
            user=user,
            completed=False,
            position_seconds__gte=MOVIE_RESUME_MIN_SECONDS,
            item__media_type=MediaTypes.MOVIE.value,
        )
        .order_by()
        .values_list("item_id", "position_seconds", "duration_seconds", "updated_at")
    ):
        if duration and position > duration * MOVIE_RESUME_MAX_FRACTION:
            continue
        resume[item_id] = (position, duration)
        resume_at[item_id] = updated_at
    movie_status: dict[int, str] = {}
    if resume:
        # A Completed movie with a resume position is a rewatch; it is the only
        # Completed movie that reaches the row.
        movie_status = dict(
            Movie.objects.filter(
                user=user,
                item_id__in=list(resume),
                status__in=(*IN_PROGRESS_MOVIE_STATUSES, Status.COMPLETED.value),
            ).values_list("item_id", "status")
        )
        # A position no newer than the movie's last finished play is stale (the
        # player never sent completed=True), not a rewatch.
        finished_at = dict(
            Movie.objects.filter(user=user, item_id__in=list(resume), end_date__isnull=False)
            .values("item_id")
            .annotate(last=Max("end_date"))
            .values_list("item_id", "last")
        )
        resume = {
            item_id: value
            for item_id, value in resume.items()
            if item_id in movie_status
            and not (
                finished_at.get(item_id) is not None
                and finished_at[item_id] >= resume_at[item_id]
            )
        }
        candidates.update({item_id: resume_at[item_id] for item_id in resume})

    if not candidates:
        return []
    items = dedupe_cross_provider_items(
        list(Item.objects.filter(id__in=candidates)),
        getattr(user, "tv_metadata_source_default", Sources.TMDB.value),
    )
    media_lookup = _media_lookup_for_items(user, items)
    entries = []
    for item in items:
        media = media_lookup.get(item.id)
        if media is None:
            continue
        entry = ContinueEntry(item=item, media=media)
        stamps = (candidates[item.id], getattr(media, "progressed_at", None))
        entry.last_activity = max((stamp for stamp in stamps if stamp), default=earliest)
        if item.media_type == MediaTypes.MOVIE.value:
            position, duration = resume[item.id]
            entry.position_seconds = position
            entry.duration_seconds = duration
            entry.remaining_seconds = duration - position if duration else None
            entry.resume_percent = (
                min(100, round(100 * position / duration)) if duration else 0
            )
            entry.is_rewatch = movie_status[item.id] == Status.COMPLETED.value
        else:
            _point_show_at_episode(
                entry, media, part_target.get((item.media_id, item.source))
            )
            if item.id in rewatch_only and entry.target_episode_number is None:
                continue
            entry.is_rewatch = bool(getattr(media, "is_rewatching", False))
            entry.watched_count, entry.released_count = show_counts.get(
                item.id, (None, None)
            )
        entries.append(entry)
    _attach_episode_items(entries)
    entries.sort(key=lambda entry: entry.last_activity, reverse=True)
    return entries[:IN_PROGRESS_LIMIT]


def _point_show_at_episode(entry, media, part: _PartWatched | None) -> None:
    """Aim a show's card at its part-watched episode, else at its next episode."""
    if (
        part is not None
        and part.season_number is not None
        and part.episode_number is not None
    ):
        entry.target_item_id = part.item_id
        entry.target_season_number = part.season_number
        entry.target_episode_number = part.episode_number
        entry.position_seconds = part.position_seconds
        entry.duration_seconds = part.duration_seconds
        if part.duration_seconds:
            entry.remaining_seconds = max(0, part.duration_seconds - part.position_seconds)
            entry.resume_percent = min(
                100, round(100 * part.position_seconds / part.duration_seconds)
            )
        return
    # The rule ct_next_episode used before the card carried its own target.
    if getattr(media, "seasons", None) is None or not callable(
        getattr(media, "next_episode_target", None)
    ):
        return
    target = media.next_episode_target()
    if target is None:
        return
    season, episode_number = target
    season_number = season.item.season_number
    if season_number is None or episode_number is None:
        return
    entry.target_season_number = season_number
    entry.target_episode_number = episode_number


def _attach_episode_items(entries: list[ContinueEntry]) -> None:
    """Fill each show target's episode Item id and title from the library, in one query."""
    targets = [entry for entry in entries if entry.target_episode_number is not None]
    if not targets:
        return
    query = Q()
    for entry in targets:
        query |= Q(
            media_id=entry.item.media_id,
            source=entry.item.source,
            season_number=entry.target_season_number,
            episode_number=entry.target_episode_number,
        )
    episodes = {
        (episode.media_id, episode.source, episode.season_number, episode.episode_number): episode
        for episode in Item.objects.filter(query, media_type=MediaTypes.EPISODE.value).only(
            "id", "media_id", "source", "season_number", "episode_number", "title"
        )
    }
    for entry in targets:
        episode = episodes.get(
            (
                entry.item.media_id,
                entry.item.source,
                entry.target_season_number,
                entry.target_episode_number,
            )
        )
        if episode is None:
            continue
        entry.target_item_id = entry.target_item_id or episode.id
        entry.target_title = episode.title or None


def _media_lookup_for_items(
    user,
    items: list[Item],
    *,
    status_filter: list[str] | None = None,
) -> dict[int, object]:
    """Map item ids to the user's media record, with statuses and progress set."""
    status_filter = status_filter or []
    items_by_media_type: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        items_by_media_type[item.media_type].append(item)

    lookup: dict[int, object] = {}
    for actual_media_type, type_items in items_by_media_type.items():
        model = apps.get_model("app", actual_media_type)
        item_ids = [item.id for item in type_items]
        if actual_media_type == MediaTypes.EPISODE.value:
            queryset = (
                model.objects.filter(
                    related_season__user=user,
                    item_id__in=item_ids,
                )
                .select_related("item")
                .defer(*(f"item__{field}" for field in HOME_CARD_UNREAD_ITEM_FIELDS))
            )
        else:
            queryset = (
                model.objects.filter(
                    user=user,
                    item_id__in=item_ids,
                )
                .select_related("item")
                .defer(*(f"item__{field}" for field in HOME_CARD_UNREAD_ITEM_FIELDS))
            )
        if actual_media_type == MediaTypes.PODCAST.value:
            queryset = queryset.select_related("show", "episode")
        if actual_media_type == MediaTypes.MUSIC.value:
            queryset = queryset.select_related("album")
        queryset = BasicMedia.objects._apply_prefetch_related(
            queryset, actual_media_type
        )
        media_entries = list(queryset)

        grouped_entries: dict[int, list[object]] = defaultdict(list)
        for media_entry in media_entries:
            grouped_entries[media_entry.item_id].append(media_entry)

        candidate_entries = []
        for entries in grouped_entries.values():
            entries = sorted(  # noqa: PLW2901  # deliberate in-loop normalisation
                entries, key=lambda entry: entry.created_at, reverse=True
            )
            primary_entry = entries[0]
            if actual_media_type != MediaTypes.PODCAST.value and len(entries) > 1:
                BasicMedia.objects._aggregate_item_data(primary_entry, entries)
            candidate_entries.append(primary_entry)

        if candidate_entries:
            BasicMedia.objects.annotate_max_progress(
                candidate_entries, actual_media_type
            )
            if actual_media_type == MediaTypes.SEASON.value:
                for primary_entry in candidate_entries:
                    if len(grouped_entries.get(primary_entry.item_id, [])) != 1:
                        continue
                    effective_status = (
                        primary_entry.derived_status_from_episode_progress()
                    )
                    if (
                        effective_status == Status.COMPLETED.value
                        and primary_entry.status != Status.COMPLETED.value
                    ):
                        primary_entry.promote_to_completed_if_fully_watched(
                            max_progress=getattr(primary_entry, "max_progress", None),
                        )
                    primary_entry.status = effective_status
                    primary_entry.aggregated_status = effective_status
            _annotate_home_card_images(candidate_entries)

            for primary_entry in candidate_entries:
                latest_status = getattr(
                    primary_entry, "aggregated_status", None
                ) or getattr(primary_entry, "status", None)
                if status_filter and latest_status not in status_filter:
                    continue
                if actual_media_type == MediaTypes.PODCAST.value:
                    primary_entry.use_podcast_show = bool(
                        getattr(primary_entry, "show", None)
                    )
                lookup[primary_entry.item_id] = primary_entry

    return lookup


def _recently_watched(user) -> list[HomeRowEntry]:
    """Return the latest watch of each show and movie, newest first."""
    # Keyed by title, so a show appears once with its latest episode's time.
    watched: dict[tuple[str, int], tuple[datetime, object]] = {}
    episodes = (
        Episode.objects.filter(related_season__user=user, end_date__isnull=False)
        .select_related("related_season__item", "related_season__related_tv__item")
        .order_by("-end_date")[:RECENT_EPISODE_SCAN]
    )
    for episode in episodes:
        season = episode.related_season
        media = season.related_tv or season
        watched.setdefault(("tv", media.item_id), (episode.end_date, media))
        if len(watched) >= RECENT_LIMIT:
            break
    movies = (
        Movie.objects.filter(user=user, end_date__isnull=False)
        .exclude(status=Status.PLANNING.value)
        .select_related("item")
        .order_by("-end_date")[:RECENT_LIMIT]
    )
    for movie in movies:
        watched.setdefault(("movie", movie.item_id), (movie.end_date, movie))
    recent = sorted(watched.values(), key=lambda pair: pair[0], reverse=True)
    return [
        HomeRowEntry(
            item=media.item,
            media=media,
            show_progress_controls=False,
            subtitle_override=timezone.localtime(watched_at).date(),
        )
        for watched_at, media in recent[:RECENT_LIMIT]
    ]


def _catch_up(user, now: datetime) -> tuple[int, int]:
    """Aired episodes not yet watched across in-progress seasons, and their shows."""
    seasons = {
        season_id: (item_id, tv_id)
        for season_id, item_id, tv_id in Season.objects.filter(
            user=user,
            status=Status.IN_PROGRESS.value,
        )
        # Same exclusions as the In Progress row, so the header and the row agree.
        .exclude(related_tv__status__in=(Status.DROPPED.value, Status.PAUSED.value))
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
    cache_key = f"{HOME_ROW_CACHE_PREFIX}_{user.id}_v5_sections_{today.isoformat()}"
    sections = cache.get(cache_key)
    if sections is None:
        airing, airing_count = _airing_this_week(user, today)
        catch_up, catch_up_shows = _catch_up(user, timezone.now())
        in_progress = build_continue_watching(user)
        sections = {
            "in_progress": in_progress,
            # The filter pills show only when both kinds are present.
            "in_progress_kinds": sorted(
                {
                    "movie" if entry.item.media_type == MediaTypes.MOVIE.value else "show"
                    for entry in in_progress
                }
            ),
            # Two columns of three on desktop (A1); phones show the first.
            "airing": [column for column in (airing[:3], airing[3:]) if column],
            "airing_count": airing_count,
            "recent": _recently_watched(user),
            "coming_soon": _coming_soon(user, today),
            "catch_up": catch_up,
            "catch_up_shows": catch_up_shows,
        }
        cache.set(cache_key, sections, HOME_ROW_CACHE_TTL)
        register_home_row_cache_key(user.id, cache_key)
    return sections
