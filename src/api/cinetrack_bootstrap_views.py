"""High-throughput CineTrack bootstrap endpoints for the Floppy fork.

These endpoints assert durable tracking facts first and deliberately keep
provider metadata hydration off the request path.  They are isolated from the
upstream-compatible tracking views so the fork remains easy to rebase.
"""

import logging
import re
import time
from collections import Counter, defaultdict
from datetime import date
from http import HTTPStatus as HTTP  # noqa: N814
from typing import NamedTuple
from uuid import UUID

from django.core.cache import cache
from django.db import OperationalError, transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.fork_services_episode import create_episode_watch
from app.models import TV, Episode, Item, MediaTypes, Movie, MoviePlay, Season, Status
from app.providers import credentials, episode_orders, services, tmdb, tvdb
from app.services import metadata_resolution
from app.services.episode_coordinates import (
    EpisodeMetadataUnavailableError,
    InvalidEpisodeCoordinateError,
    resolve_episode_coordinate,
)
from app.services.sync_activity import batched_activity, touch_activity
from app.services.sync_items import refresh_sync_items
from app.services.watch_state import project_watch_state_for_change, suspend_projection
from app.tasks_metadata_cache import queue_cinetrack_bootstrap_hydration

from .contract_serializers import DetailErrorSerializer
from .helpers import check_source_type, try_parse_datetime_input
from .schema import MEDIA_TYPE_TV_ONLY_PARAM

logger = logging.getLogger(__name__)
# SQLite allows one writer; on "database is locked" the episode write retries
# after these pauses, then answers 503 so the client retries the request later.
DB_LOCK_BACKOFF_SECONDS = (0.5, 1.5, 3.0)
DB_BUSY_RETRY_AFTER_SECONDS = 30
MAX_BOOTSTRAP_ITEMS = 50
MAX_EPISODE_EVENTS = 50
MAX_TRANSLATE_EPISODES = 400
SLOW_EPISODE_ENSURE_MS = 5_000
MSG_EVENT_CONFLICT = "client_event_id belongs to another episode event."
MSG_EVENT_RACE = "client_event_id conflicts with an existing episode event."
MSG_RESOLVE_FAILED = "Could not resolve episode events."
MSG_ENSURE_FAILED = "Could not ensure episode events."
MSG_DB_BUSY = "Floppy database is busy; retry shortly."
_STATUS_BY_CODE = {
    0: Status.PLANNING.value,
    1: Status.IN_PROGRESS.value,
    2: Status.PAUSED.value,
    3: Status.COMPLETED.value,
    4: Status.DROPPED.value,
}


class CineTrackMovieWatchInputSerializer(serializers.Serializer):
    """One exact historical movie-watch event."""

    watched_at = serializers.DateTimeField()
    client_event_id = serializers.CharField(max_length=255)


class CineTrackMovieInputSerializer(serializers.Serializer):
    """One movie state assertion in a CineTrack bootstrap batch."""

    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True)
    status = serializers.JSONField(required=False)
    watch = CineTrackMovieWatchInputSerializer(required=False, allow_null=True)


class CineTrackMoviesEnsureRequestSerializer(serializers.Serializer):
    """A batch of movies to ensure."""

    movies = CineTrackMovieInputSerializer(many=True)


class CineTrackShowInputSerializer(serializers.Serializer):
    """One show to ensure, identified by provider IDs."""

    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True)
    status = serializers.JSONField(required=False)


class CineTrackShowsEnsureRequestSerializer(serializers.Serializer):
    """A batch of shows to ensure."""

    shows = CineTrackShowInputSerializer(many=True)


class CineTrackEpisodeEventInputSerializer(serializers.Serializer):
    """One episode watch event to ensure."""

    season_number = serializers.IntegerField(min_value=0)
    episode_number = serializers.IntegerField(min_value=1)
    watched_at = serializers.DateTimeField()
    client_event_id = serializers.UUIDField()


class CineTrackEpisodeEnsureRequestSerializer(serializers.Serializer):
    """A batch of episode watch events to ensure."""

    events = CineTrackEpisodeEventInputSerializer(many=True)
    library_media_type = serializers.CharField(required=False, allow_blank=True)


class CineTrackEpisodeTranslateInputSerializer(serializers.Serializer):
    """One episode coordinate to translate between providers."""

    season = serializers.IntegerField(min_value=0)
    episode = serializers.IntegerField(min_value=1)
    watched_at = serializers.DateTimeField(required=False)


class CineTrackEpisodeTranslateRequestSerializer(serializers.Serializer):
    """A batch of episode coordinates to translate."""

    locals()["from"] = serializers.ChoiceField(
        choices=["tracker", "tmdb"],
        help_text="Numbering of the submitted episodes: a tracker's own or TMDB's.",
    )
    episodes = CineTrackEpisodeTranslateInputSerializer(many=True)


class CineTrackEpisodeCoordinateSerializer(serializers.Serializer):
    """A season and episode number pair."""

    season = serializers.IntegerField()
    episode = serializers.IntegerField()


class CineTrackEpisodeTranslateResultSerializer(serializers.Serializer):
    """The translation of one episode coordinate."""

    season = serializers.IntegerField()
    episode = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["same", "translated", "not_found", "metadata_unavailable"])
    tmdb = CineTrackEpisodeCoordinateSerializer(allow_null=True)
    absolute = serializers.IntegerField(allow_null=True)
    tvdb = CineTrackEpisodeCoordinateSerializer(allow_null=True)
    reason = serializers.CharField(allow_null=True)


class CineTrackEpisodeTranslateResponseSerializer(serializers.Serializer):
    """The translations for a batch of episode coordinates."""

    results = CineTrackEpisodeTranslateResultSerializer(many=True)


class CineTrackBootstrapResultSerializer(serializers.Serializer):
    """The outcome for one ensured item."""

    source = serializers.CharField(required=False)
    media_id = serializers.CharField(required=False)
    client_event_id = serializers.CharField(required=False)
    season_number = serializers.IntegerField(required=False)
    episode_number = serializers.IntegerField(required=False)
    # Present when an episode was stored at a different (TMDB) coordinate than
    # submitted, e.g. a continuous anime number translated to its season.
    stored_season_number = serializers.IntegerField(required=False)
    stored_episode_number = serializers.IntegerField(required=False)
    # Episode events may also be not_found (the provider's season list lacks
    # that episode number) or metadata_unavailable (no authoritative list);
    # those events were not written and the rest of the batch was.
    status = serializers.ChoiceField(
        choices=("created", "already_satisfied", "not_found", "metadata_unavailable"),
    )
    # Short machine-readable cause for not_found/metadata_unavailable, so the
    # client can log why an episode could not be placed.
    reason = serializers.CharField(required=False)
    # The episode's title as TVDB knows it, for an event that could not be
    # placed, so the client can point the user to it (e.g. a special TMDB
    # files as a movie).
    title = serializers.CharField(required=False)


class CineTrackBootstrapResponseSerializer(serializers.Serializer):
    """The outcomes for a batch of ensured items."""

    results = CineTrackBootstrapResultSerializer(many=True)


# A 200 reports one result per submitted entry: created/already_satisfied are
# written, not_found/metadata_unavailable (episodes only) were not. Any other
# failure is a whole-request error and nothing is acknowledged.
BOOTSTRAP_RESPONSES = {
    200: CineTrackBootstrapResponseSerializer,
    400: OpenApiResponse(DetailErrorSerializer, description="Malformed or oversized batch; nothing was written."),
    404: OpenApiResponse(DetailErrorSerializer, description="Episode metadata could not be fetched; nothing was written."),
    409: OpenApiResponse(DetailErrorSerializer, description="client_event_id already belongs to another event."),
    500: OpenApiResponse(DetailErrorSerializer, description="The batch could not be written; retry is safe."),
    503: OpenApiResponse(DetailErrorSerializer, description="Database busy; nothing was written. Retry after Retry-After seconds."),
}


def _parse_status(raw_value, *, default=Status.IN_PROGRESS.value):
    """Accept Floppy status labels or the API's stable numeric status codes."""
    if raw_value in (None, ""):
        return default
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        for candidate in Status.values:
            if stripped.lower() == candidate.lower():
                return candidate
        raw_value = stripped
    try:
        return _STATUS_BY_CODE[int(raw_value)]
    except (KeyError, TypeError, ValueError):
        return None


def _item_key(source, media_id):
    return str(source), str(media_id)


def _minimal_item(*, source, media_id, media_type, title, image="", library_media_type=""):
    return Item.objects.create(
        source=source,
        media_id=str(media_id),
        media_type=media_type,
        library_media_type=library_media_type,
        title=title,
        original_title=title or None,
        image=image or "",
    )


def _tv_queryset(user, media_id, source, library_media_type=""):
    queryset = TV.objects.filter(
        user=user,
        item__media_id=str(media_id),
        item__source=source,
        item__media_type=MediaTypes.TV.value,
        item__season_number__isnull=True,
    ).select_related("item")
    if library_media_type:
        queryset = queryset.filter(item__library_media_type=library_media_type)
    else:
        queryset = queryset.exclude(item__library_media_type=MediaTypes.ANIME.value)
    return queryset.order_by("id")


def _ensure_parent_tv(user, media_id, source, metadata, library_media_type=""):
    """Resolve/create the parent TV row without another provider request."""
    existing = _tv_queryset(user, media_id, source, library_media_type).first()
    if existing is not None:
        return existing

    item_queryset = Item.objects.filter(
        media_id=str(media_id),
        source=source,
        media_type=MediaTypes.TV.value,
        season_number__isnull=True,
    )
    if library_media_type:
        item_queryset = item_queryset.filter(library_media_type=library_media_type)
    else:
        item_queryset = item_queryset.exclude(library_media_type=MediaTypes.ANIME.value)
    item = item_queryset.order_by("id").first()
    if item is None:
        fallback_title = str(metadata.get("title") or f"CineTrack show {media_id}")
        item = _minimal_item(
            source=source,
            media_id=media_id,
            media_type=MediaTypes.TV.value,
            title=fallback_title,
            image=metadata.get("image") or "",
            library_media_type=library_media_type,
        )

    tv = TV(
        user=user,
        item=item,
        status=Status.IN_PROGRESS.value,
        score=None,
        notes="",
        created_at=timezone.now(),
    )
    tv.save_base(raw=True, force_insert=True)
    return tv


def _ensure_season_from_metadata(
    user,
    media_id,
    source,
    season_number,
    *,
    combined_metadata,
    season_metadata,
    library_media_type="",
):
    """Resolve/create one tracked season using already-fetched metadata."""
    existing = metadata_resolution.find_tracked_season(
        user,
        media_id,
        source,
        season_number,
        library_media_type=library_media_type or None,
    )
    if existing is not None:
        return existing

    parent_tv = _ensure_parent_tv(
        user,
        media_id,
        source,
        combined_metadata,
        library_media_type,
    )
    season_image = season_metadata.get("image") or combined_metadata.get("image") or ""
    season_item = metadata_resolution.get_or_create_tracked_season_item(
        media_id,
        source,
        season_number,
        provider=source,
        library_media_type=library_media_type or MediaTypes.SEASON.value,
        metadata=None,
        defaults={
            **Item.title_fields_from_metadata(
                season_metadata or combined_metadata,
                fallback_title=parent_tv.item.title,
            ),
            "image": season_image,
        },
    )
    season = Season(
        item=season_item,
        user=user,
        related_tv=parent_tv,
        score=None,
        status=Status.IN_PROGRESS.value,
        notes="",
        created_at=timezone.now(),
    )
    season.save_base(raw=True, force_insert=True)
    return season


class MovieEnsureOutcome(NamedTuple):
    """What one movie entry did: its outcome label and what changed."""

    outcome: str
    created: bool
    changed: bool


def _conflicted_movie_entries(user, parsed):
    """Indexes of entries whose external id is bound to another movie or instant."""
    external_ids = {e["external_id"] for e in parsed if e["external_id"]}
    if not external_ids:
        return set()
    bound_plays = defaultdict(list)
    for play in MoviePlay.objects.filter(
        movie__user=user,
        external_id__in=external_ids,
    ).select_related("movie__item"):
        bound_plays[play.external_id].append(play)
    conflicted = set()
    for index, entry in enumerate(parsed):
        bound = bound_plays.get(entry["external_id"])
        if not bound or entry["watched_at"] is None:
            continue
        if not any(
            (str(play.movie.item.media_id), play.movie.item.source, play.end_date)
            == (entry["media_id"], entry["source"], entry["watched_at"])
            for play in bound
        ):
            conflicted.add(index)
    return conflicted


def ensure_movie_entries(user, parsed, *, detect_conflicts=False, complete_on_advance=False):
    """Ensure movie rows (and exact plays) for parsed entries, one outcome each.

    ``parsed`` holds dicts with source, media_id, title, image, status (None
    keeps the stored status), watched_at and external_id. With
    ``detect_conflicts`` an external id already bound to a different movie or
    instant yields ``conflict`` for that entry only, and nothing is created for
    it. With ``complete_on_advance`` a play that advances the movie's last watch
    marks it completed, like ``Movie.watch``; it also reports play-level
    outcomes for retried plays.
    """
    conflicted = _conflicted_movie_entries(user, parsed) if detect_conflicts else set()
    work = [entry for index, entry in enumerate(parsed) if index not in conflicted]
    rows = iter(
        _ensure_movie_rows(
            user,
            work,
            play_level_outcomes=detect_conflicts,
            complete_on_advance=complete_on_advance,
        )
        if work
        else [],
    )
    return [
        MovieEnsureOutcome("conflict", False, False) if index in conflicted else next(rows)
        for index in range(len(parsed))
    ]


@transaction.atomic
def _ensure_movie_rows(user, parsed, *, play_level_outcomes, complete_on_advance):
    outcomes = []
    # Projection is a recompute per save; run it once per touched movie instead,
    # after status and end_date are written (it reads both).
    with transaction.atomic(), suspend_projection():
        sources = {entry["source"] for entry in parsed}
        media_ids = {entry["media_id"] for entry in parsed}
        items = {
            _item_key(item.source, item.media_id): item
            for item in Item.objects.filter(
                media_type=MediaTypes.MOVIE.value,
                source__in=sources,
                media_id__in=media_ids,
            )
        }
        hydration_ids = []
        for entry in parsed:
            key = _item_key(entry["source"], entry["media_id"])
            if key not in items:
                items[key] = _minimal_item(
                    source=entry["source"],
                    media_id=entry["media_id"],
                    media_type=MediaTypes.MOVIE.value,
                    title=entry["title"],
                    image=entry["image"],
                )
                hydration_ids.append(items[key].id)

        item_ids = [items[_item_key(e["source"], e["media_id"])].id for e in parsed]
        items_by_id = {item.id: item for item in items.values()}
        movies = {
            movie.item_id: movie
            for movie in Movie.objects.filter(user=user, item_id__in=item_ids)
        }
        # One insert for the batch. Every Movie receiver but watch-state
        # projection skips raw saves anyway; projection runs once at the end.
        new_movies = Movie.objects.bulk_create([
            Movie(
                user=user,
                item=items_by_id[item_id],
                status=Status.IN_PROGRESS.value,
                score=None,
                notes="",
                created_at=timezone.now(),
            )
            for item_id in dict.fromkeys(item_ids)
            if item_id not in movies
        ])
        movies.update({movie.item_id: movie for movie in new_movies})
        created_movie_ids = {movie.id for movie in new_movies}

        external_ids = {e["external_id"] for e in parsed if e["external_id"]}
        existing_plays = {
            (play.movie_id, play.external_id): play
            for play in MoviePlay.objects.filter(
                movie_id__in=[movie.id for movie in movies.values()],
                external_id__in=external_ids,
            )
        }
        watch_dates = {e["watched_at"] for e in parsed if e["watched_at"] is not None}
        # A play stored at the exact same instant is the same watch whatever
        # external id it carries (none, an importer's, or one from an
        # earlier CineTrack connection), matching the episode endpoint.
        legacy_plays = defaultdict(list)
        if watch_dates:
            for play in MoviePlay.objects.filter(
                movie_id__in=[movie.id for movie in movies.values()],
                end_date__in=watch_dates,
            ).order_by("id"):
                legacy_plays[(play.movie_id, play.end_date)].append(play)

        dirty_movies = {}
        touched_movies = {movie.id: movie for movie in new_movies}
        for entry in parsed:
            item = items[_item_key(entry["source"], entry["media_id"])]
            movie = movies[item.id]
            watched_at = entry["watched_at"]
            external_id = entry["external_id"]
            changed = movie.id in created_movie_ids
            if entry["status"] is not None and movie.status != entry["status"]:
                movie.status = entry["status"]
                changed = True

            outcome = "created" if movie.id in created_movie_ids else "already_satisfied"
            if watched_at is not None:
                play = existing_plays.get((movie.id, external_id))
                if play is None:
                    legacy_candidates = legacy_plays.get((movie.id, watched_at), [])
                    if legacy_candidates:
                        play = legacy_candidates.pop(0)
                        if not play.external_id:
                            # Identity adoption only; never overwrite another id.
                            play.external_id = external_id
                            play.save(update_fields=["external_id"])
                            touched_movies[movie.id] = movie
                        existing_plays[(movie.id, external_id)] = play
                        outcome = "already_satisfied"
                    elif movie.end_date == watched_at and not movie.plays.exists():
                        play, _ = MoviePlay.objects.get_or_create(
                            movie=movie,
                            external_id=external_id,
                            defaults={"end_date": watched_at},
                        )
                        existing_plays[(movie.id, external_id)] = play
                        touched_movies[movie.id] = movie
                        outcome = "already_satisfied"
                    else:
                        play, created = MoviePlay.objects.get_or_create(
                            movie=movie,
                            external_id=external_id,
                            defaults={"end_date": watched_at},
                        )
                        existing_plays[(movie.id, external_id)] = play
                        touched_movies[movie.id] = movie
                        outcome = "created" if created else "already_satisfied"
                elif play_level_outcomes:
                    outcome = "already_satisfied"
                if movie.end_date is None or watched_at > movie.end_date:
                    movie.end_date = watched_at
                    if complete_on_advance:
                        movie.status = Status.COMPLETED.value
                    changed = True
            if changed:
                dirty_movies[movie.id] = movie
                touched_movies[movie.id] = movie
            outcomes.append(
                MovieEnsureOutcome(outcome, movie.id in created_movie_ids, changed),
            )

        if dirty_movies:
            Movie.objects.bulk_update(
                list(dirty_movies.values()),
                fields=["status", "end_date"],
            )
            touch_activity(user, "library")
            # bulk_update fires no signals; keep the main-tracker index exact.
            refresh_sync_items(
                user,
                [movie.item for movie in dirty_movies.values()],
            )
        queue_cinetrack_bootstrap_hydration(hydration_ids, user.id)
    for movie in touched_movies.values():
        project_watch_state_for_change(user, items_by_id[movie.item_id])
    return outcomes


class ShowEnsureOutcome(NamedTuple):
    """What one show entry did: whether its row was created or its status changed."""

    created: bool
    changed: bool


def ensure_show_entries(user, parsed):
    """Ensure show rows and statuses without manufacturing episode history.

    ``parsed`` holds dicts with source, media_id, title, image and status.
    Never creates Episode rows, whatever the status (completed included).
    """
    outcomes = []
    with transaction.atomic():
        sources = {entry["source"] for entry in parsed}
        media_ids = {entry["media_id"] for entry in parsed}
        items = {
            _item_key(item.source, item.media_id): item
            for item in Item.objects.filter(
                media_type=MediaTypes.TV.value,
                source__in=sources,
                media_id__in=media_ids,
                season_number__isnull=True,
            ).exclude(library_media_type=MediaTypes.ANIME.value)
        }
        # The user's own show row wins, also when it is filed as anime:
        # otherwise a status change would start a second copy of the show.
        own = {}
        for tv in TV.objects.filter(
            user=user,
            item__media_type=MediaTypes.TV.value,
            item__source__in=sources,
            item__media_id__in=media_ids,
            item__season_number__isnull=True,
        ).select_related("item").order_by("id"):
            own.setdefault(_item_key(tv.item.source, tv.item.media_id), tv.item)
        items.update(own)
        hydration_ids = []
        for entry in parsed:
            key = _item_key(entry["source"], entry["media_id"])
            if key not in items:
                items[key] = _minimal_item(
                    source=entry["source"],
                    media_id=entry["media_id"],
                    media_type=MediaTypes.TV.value,
                    title=entry["title"],
                    image=entry["image"],
                )
                hydration_ids.append(items[key].id)

        item_ids = [items[_item_key(e["source"], e["media_id"])].id for e in parsed]
        items_by_id = {item.id: item for item in items.values()}
        tv_rows = {
            tv.item_id: tv
            for tv in TV.objects.filter(user=user, item_id__in=item_ids)
        }
        dirty = []
        # One insert for the batch. TV receivers skip raw saves except the sync
        # index, which refresh_sync_items below covers: new rows are all dirty.
        new_rows = TV.objects.bulk_create([
            TV(
                user=user,
                item=items_by_id[item_id],
                status=Status.IN_PROGRESS.value,
                score=None,
                notes="",
                created_at=timezone.now(),
            )
            for item_id in dict.fromkeys(item_ids)
            if item_id not in tv_rows
        ])
        tv_rows.update({tv.item_id: tv for tv in new_rows})
        created_ids = {tv.id for tv in new_rows}

        for entry in parsed:
            item = items[_item_key(entry["source"], entry["media_id"])]
            tv = tv_rows[item.id]
            changed = tv.id in created_ids
            if tv.status != entry["status"]:
                tv.status = entry["status"]
                changed = True
            if changed:
                dirty.append(tv)
            outcomes.append(ShowEnsureOutcome(tv.id in created_ids, changed))

        if dirty:
            TV.objects.bulk_update(dirty, fields=["status"])
            touch_activity(user, "library")
            # bulk_update fires no signals; keep the main-tracker index exact.
            refresh_sync_items(user, [tv.item for tv in dirty])
        queue_cinetrack_bootstrap_hydration(hydration_ids, user.id)
    return outcomes


class EpisodeEnsureError(Exception):
    """A request-level failure of :func:`ensure_episode_events`.

    ``kind`` is one of conflict (a client_event_id belongs to another event),
    metadata (the provider's episode list could not be fetched), busy (the
    database stayed locked) or error (any other write failure).
    """

    def __init__(self, detail, status, *, headers=None, kind="error", partial=None):
        """Carry the response detail, HTTP status, headers, kind and partial outcomes."""
        super().__init__(detail)
        self.detail = detail
        self.status = status
        self.headers = headers
        self.kind = kind
        # Outcomes settled before the failure (claimed or already-stored
        # events); the events still missing from it were not written.
        self.partial = partial


class EpisodeEnsureResult(NamedTuple):
    """Per-event results of :func:`ensure_episode_events`, keyed by event id."""

    outcomes: dict
    stored: dict
    reasons: dict
    titles: dict


class _CoordinateMetadataError(Exception):
    """The provider's episode list could not be fetched (already logged)."""


class CoordinateResolution(NamedTuple):
    """Where each submitted episode coordinate lands on the provider's listing.

    ``resolvable`` holds ``(season, episode, watched_at, key)`` at the TMDB
    coordinate; ``stored`` maps key to that coordinate when it differs from the
    submitted one. Events missing from ``resolvable`` have an ``outcomes``
    entry (``not_found`` or ``metadata_unavailable``) and usually a reason.
    """

    resolvable: list
    stored: dict
    outcomes: dict
    reasons: dict
    titles: dict
    metadata_by_season: dict
    combined_metadata: dict | None
    show_unknown: bool = False


def resolve_episode_coordinates(user, source, media_id, events, *, timings=None):
    """Resolve submitted episode coordinates onto TMDB's, with no play writes.

    ``events`` is a non-empty list of ``(season, episode, watched_at, key)``
    tuples with unique keys; ``watched_at`` may be None (the stages never use
    it). Fetches the metadata once, then tries the exact coordinate, absolute
    numbers listed in TMDB seasons, the absolute walk over regular seasons and
    TVDB identity matching. Raises :class:`_CoordinateMetadataError` on a
    request-level metadata failure; a provider 404 yields ``show_unknown``.
    """
    timings = {} if timings is None else timings
    stored = {}
    outcomes = {}
    reasons = {}
    titles = {}
    season_numbers = sorted({event[0] for event in events})
    stage_started = time.monotonic()
    try:
        combined_metadata = services.get_media_metadata(
            "tv_with_seasons",
            media_id,
            source,
            season_numbers,
        )
        timings["metadata_ms"] = int((time.monotonic() - stage_started) * 1000)
    except services.ProviderAPIError as error:
        if error.status_code != HTTP.NOT_FOUND:
            logger.exception("CineTrack episode metadata batch failed media_id=%s", media_id)
            raise _CoordinateMetadataError from None
        # The provider itself says the show does not exist (a deleted or
        # merged TMDB id): a definite verdict for every event, never history.
        logger.warning("CineTrack episode ensure show unknown to provider media_id=%s", media_id)
        for _season, _episode, _watched_at, client_event_id in events:
            outcomes[client_event_id] = "not_found"
            reasons[client_event_id] = "unknown_to_provider"
        return CoordinateResolution([], stored, outcomes, reasons, titles, {}, None, show_unknown=True)
    except Exception:
        logger.exception("CineTrack episode metadata batch failed media_id=%s", media_id)
        raise _CoordinateMetadataError from None

    metadata_by_season = {}
    for season_number in season_numbers:
        season_metadata = combined_metadata.get(f"season/{season_number}")
        if not isinstance(season_metadata, dict) and len(season_numbers) == 1 and isinstance(combined_metadata.get("episodes"), list):
            season_metadata = combined_metadata
        if not isinstance(season_metadata, dict):
            continue
        # Avoid a secondary TVDB artwork lookup in the bootstrap request;
        # the authoritative episode list is already present and rich
        # metadata can be hydrated asynchronously later.
        season_metadata.setdefault("_tvdb_episode_image_map", {})
        metadata_by_season[season_number] = season_metadata

    # Events the provider does not know (different episode numbering,
    # missing season list) are reported per event; the rest of the
    # batch is still applied. A sync import never deletes history.
    resolvable = []
    absolute_candidates = []
    identity_candidates = []
    listed_seasons = _listed_season_numbers(combined_metadata)
    for event in events:
        season_number, episode_number, _, client_event_id = event
        if season_number not in metadata_by_season:
            # A season TMDB does not have at all is a numbering
            # difference, not a temporary metadata gap.
            if listed_seasons and season_number not in listed_seasons:
                identity_candidates.append(event)
            else:
                outcomes[client_event_id] = "metadata_unavailable"
                reasons[client_event_id] = "season_metadata_missing"
            continue
        try:
            resolve_episode_coordinate(
                media_id,
                source,
                season_number,
                episode_number,
                season_metadata=metadata_by_season[season_number],
            )
        except InvalidEpisodeCoordinateError:
            if season_number == 1:
                absolute_candidates.append(event)
            else:
                identity_candidates.append(event)
            continue
        except EpisodeMetadataUnavailableError:
            outcomes[client_event_id] = "metadata_unavailable"
            reasons[client_event_id] = "season_metadata_missing"
            continue
        resolvable.append(event)

    # Exact identity first: some TMDB shows keep the absolute episode
    # numbers inside their seasons (One Piece S06 lists 144-195,
    # Naruto Shippuden S20 lists 459-...). The absolute number the
    # tracker sent then names the episode itself; no counting and no
    # air dates, which TMDB and TVDB often disagree on by days.
    absolutely_numbered = False
    if absolute_candidates:
        try:
            _load_listed_seasons(media_id, source, combined_metadata, metadata_by_season)
        except Exception as error:
            logger.warning(
                "CineTrack season metadata for absolute numbers failed media_id=%s error=%s",
                media_id,
                type(error).__name__,
            )
        else:
            absolutely_numbered = bool(_absolutely_numbered_seasons(metadata_by_season))
            numbered = _absolute_number_targets(media_id, source, metadata_by_season, absolute_candidates)
            remaining = []
            for event in absolute_candidates:
                target = numbered.get(event[3])
                if target is None:
                    remaining.append(event)
                    continue
                resolvable.append((target[0], target[1], event[2], event[3]))
                stored[event[3]] = target
            absolute_candidates = remaining

    # Anime trackers number a series continuously in one season, while
    # TMDB splits it into seasons. Translate those numbers by walking
    # TMDB's regular seasons, and keep only targets TMDB really lists.
    targets = _absolute_targets(combined_metadata, metadata_by_season.get(1), absolute_candidates)
    missing_seasons = sorted({season for season, _ in targets.values()} - set(metadata_by_season))
    if missing_seasons:
        try:
            extra_metadata = services.get_media_metadata("tv_with_seasons", media_id, source, missing_seasons)
        except Exception:
            logger.exception("CineTrack episode metadata batch failed media_id=%s", media_id)
            extra_metadata = {}
        for season_number in missing_seasons:
            season_metadata = extra_metadata.get(f"season/{season_number}")
            if isinstance(season_metadata, dict):
                season_metadata.setdefault("_tvdb_episode_image_map", {})
                metadata_by_season[season_number] = season_metadata
    for event in absolute_candidates:
        _season, _episode, watched_at, client_event_id = event
        target = targets.get(client_event_id)
        if target is None or target[0] not in metadata_by_season:
            identity_candidates.append(event)
            continue
        try:
            resolve_episode_coordinate(
                media_id,
                source,
                target[0],
                target[1],
                season_metadata=metadata_by_season[target[0]],
            )
        except (InvalidEpisodeCoordinateError, EpisodeMetadataUnavailableError):
            identity_candidates.append(event)
            continue
        resolvable.append((target[0], target[1], watched_at, client_event_id))
        stored[client_event_id] = target

    # Trackers that follow TVDB numbering disagree with TMDB on merged
    # two-part episodes, specials and split seasons. Match those by
    # identity instead: TVDB's record of the submitted number gives an
    # air date and title, which pick the TMDB episode. A season with an
    # unknown number is proven to be numbered differently, so its other
    # events are re-matched too rather than stored one slot off.
    if identity_candidates:
        differing_seasons = {event[0] for event in identity_candidates}
        # Season 1 of an absolutely numbered show matches TMDB exactly;
        # its unknown numbers are continuous numbering, not a shift.
        rematch = [
            event for event in resolvable
            if event[0] in differing_seasons and event[3] not in stored
            and not (event[0] == 1 and absolutely_numbered)
        ]
        stage_started = time.monotonic()
        matched, unavailable, why, names = _identity_targets(
            user,
            media_id,
            source,
            combined_metadata,
            metadata_by_season,
            identity_candidates + rematch,
        )
        timings["tvdb_ms"] = int((time.monotonic() - stage_started) * 1000)
        for _season, _episode, _watched_at, client_event_id in identity_candidates:
            if client_event_id in unavailable:
                outcomes[client_event_id] = "metadata_unavailable"
            elif client_event_id not in matched:
                outcomes[client_event_id] = "not_found"
            if client_event_id in why and client_event_id not in matched:
                reasons[client_event_id] = why[client_event_id]
                if names.get(client_event_id):
                    titles[client_event_id] = names[client_event_id]
        resolved_ids = {event[3] for event in rematch if event[3] in matched}
        resolvable = [event for event in resolvable if event[3] not in resolved_ids]
        for season_number, episode_number, watched_at, client_event_id in identity_candidates + rematch:
            target = matched.get(client_event_id)
            if target is None:
                continue
            resolvable.append((target[0], target[1], watched_at, client_event_id))
            if target != (season_number, episode_number):
                stored[client_event_id] = target
    return CoordinateResolution(resolvable, stored, outcomes, reasons, titles, metadata_by_season, combined_metadata)


def ensure_episode_events(
    user,
    source,
    media_id,
    parsed,
    *,
    repair=False,
    library_media_type="",
    conflicts="raise",
    timings=None,
):
    """Place exact episode-watch events of one show, with one metadata fetch.

    ``parsed`` is a list of ``(season_number, episode_number, watched_at,
    client_event_id)`` tuples with unique UUID ids. Must run inside
    ``credentials.current_user_scope``. Returns an :class:`EpisodeEnsureResult`
    with an outcome for every event. A client_event_id already bound to a
    different event raises :class:`EpisodeEnsureError` (``conflicts="raise"``)
    or yields the per-event outcome ``conflict`` (``conflicts="item"``). Other
    request-level failures always raise :class:`EpisodeEnsureError`.
    """
    started = time.monotonic()
    # A caller may pass a dict to read the stage timings (the profiler does).
    timings = {} if timings is None else timings
    # One-time repair re-send: place every event by the current rules and
    # move its own play there when an older version stored it elsewhere.
    instant_counts = Counter(event[2] for event in parsed)
    relocated = 0

    client_ids = [event[3] for event in parsed]
    claimed_by_id = {
        episode.watch_operation_id: episode
        for episode in Episode.objects.filter(
            watch_operation_id__in=client_ids,
        ).select_related("related_season__item", "item")
    }
    outcomes = {}
    # client_event_id -> (season, episode) actually stored, when it differs
    # from the submitted coordinate (absolute anime numbering translated).
    stored = {}
    # client_event_id -> why an event could not be placed (not_found etc.).
    reasons = {}
    # client_event_id -> TVDB episode title of an event not placed.
    titles = {}
    unresolved = []
    for season_number, episode_number, watched_at, client_event_id in parsed:
        claimed = claimed_by_id.get(client_event_id)
        if claimed is None:
            unresolved.append((season_number, episode_number, watched_at, client_event_id))
            continue
        claimed_coordinate = (claimed.related_season.item.season_number, claimed.item.episode_number)
        same_coordinate = claimed_coordinate == (season_number, episode_number)
        # An earlier attempt of this same event may have stored it at its
        # translated TMDB coordinate (absolute anime number, TVDB identity).
        translated_retry = not same_coordinate
        same_identity = (
            claimed.related_season.user_id == user.id
            and str(claimed.related_season.item.media_id) == str(media_id)
            and claimed.related_season.item.source == source
            and claimed.end_date == watched_at
            and (same_coordinate or translated_retry)
        )
        if not same_identity:
            if conflicts == "item":
                outcomes[client_event_id] = "conflict"
                continue
            raise EpisodeEnsureError(
                MSG_EVENT_CONFLICT,
                HTTP.CONFLICT,
                kind="conflict",
            )
        outcomes[client_event_id] = "already_satisfied"
        if translated_retry:
            stored[client_event_id] = claimed_coordinate

    # A play already stored at the exact same instant is the same watch,
    # whoever recorded it (live tracking, an import, an earlier CineTrack
    # connection). Resolve those before any provider metadata is fetched,
    # so re-sending already-synced history costs no provider call. A repair
    # re-send skips this shortcut: the play found there may be the one an
    # older version stored on the wrong episode.
    if unresolved and not repair:
        stage_started = time.monotonic()
        # Episodes an earlier request translated (anime absolute numbers,
        # TVDB numbering) are looked up where they were stored, so a re-send
        # finds them without fetching TMDB or TVDB again.
        translations = _remembered_translations(source, media_id)
        lookup = {
            event[3]: translations.get((event[0], event[1]), (event[0], event[1]))
            for event in unresolved
        }
        existing = defaultdict(list)
        for row in (
            Episode.objects.filter(
                related_season__user=user,
                related_season__item__media_id=str(media_id),
                related_season__item__source=source,
                related_season__item__season_number__in={coordinate[0] for coordinate in lookup.values()},
                item__episode_number__in={coordinate[1] for coordinate in lookup.values()},
                end_date__in={event[2] for event in unresolved},
            )
            .select_related("related_season__item", "item")
            .order_by("id")
        ):
            existing[(row.related_season.item.season_number, row.item.episode_number, row.end_date)].append(row)
        still_unresolved = []
        for season_number, episode_number, watched_at, client_event_id in unresolved:
            coordinate = lookup[client_event_id]
            candidates = existing.get((*coordinate, watched_at), [])
            if not candidates:
                still_unresolved.append((season_number, episode_number, watched_at, client_event_id))
                continue
            row = candidates.pop(0)
            if row.watch_operation_id is None:
                # Identity adoption only; never overwrite another event's id.
                Episode.objects.filter(pk=row.pk, watch_operation_id__isnull=True).update(
                    watch_operation_id=client_event_id,
                )
            outcomes[client_event_id] = "already_satisfied"
            if coordinate != (season_number, episode_number):
                stored[client_event_id] = coordinate
        unresolved = still_unresolved
        timings["match_ms"] = int((time.monotonic() - stage_started) * 1000)
    timings["unresolved"] = len(unresolved)

    if unresolved:
        try:
            resolution = resolve_episode_coordinates(user, source, media_id, unresolved, timings=timings)
        except _CoordinateMetadataError:
            raise EpisodeEnsureError(
                MSG_RESOLVE_FAILED,
                HTTP.NOT_FOUND,
                kind="metadata",
                partial=EpisodeEnsureResult(dict(outcomes), dict(stored), dict(reasons), dict(titles)),
            ) from None
        outcomes.update(resolution.outcomes)
        stored.update(resolution.stored)
        reasons.update(resolution.reasons)
        titles.update(resolution.titles)
        if resolution.show_unknown:
            return EpisodeEnsureResult(outcomes, stored, reasons, titles)
        combined_metadata = resolution.combined_metadata
        metadata_by_season = resolution.metadata_by_season
        unresolved = resolution.resolvable
        season_numbers = sorted({event[0] for event in unresolved})

        # Background jobs (credits, statistics, hydration) also write to SQLite;
        # a locked write is rolled back whole, so retrying it is safe.
        late_conflict = False
        settled = EpisodeEnsureResult(dict(outcomes), dict(stored), dict(reasons), dict(titles))
        for attempt in range(len(DB_LOCK_BACKOFF_SECONDS) + 1):
            created_any = False
            created_days = set()
            try:
                with transaction.atomic():
                    seasons = {}
                    for season_number in season_numbers:
                        seasons[season_number] = _ensure_season_from_metadata(
                            user,
                            media_id,
                            source,
                            season_number,
                            combined_metadata=combined_metadata,
                            season_metadata=metadata_by_season[season_number],
                            library_media_type=library_media_type,
                        )

                    season_ids = [season.id for season in seasons.values()]
                    episode_numbers = {event[1] for event in unresolved}
                    watched_dates = {event[2] for event in unresolved}
                    legacy_by_key = defaultdict(list)
                    for legacy in Episode.objects.filter(
                        related_season_id__in=season_ids,
                        item__episode_number__in=episode_numbers,
                        end_date__in=watched_dates,
                    ).select_related("item").order_by("id"):
                        legacy_by_key[(
                            legacy.related_season_id,
                            legacy.item.episode_number,
                            legacy.end_date,
                        )].append(legacy)

                    written = set()
                    for season_number, episode_number, watched_at, client_event_id in unresolved:
                        season = seasons[season_number]
                        legacy_key = (season.id, episode_number, watched_at)
                        # Both halves of a merged two-parter can land on one
                        # TMDB episode at the same instant: that is one watch,
                        # exactly as a later batch would see it.
                        if legacy_key in written:
                            outcomes[client_event_id] = "already_satisfied"
                            continue
                        written.add(legacy_key)
                        legacy_candidates = legacy_by_key.get(legacy_key, [])
                        if (
                            repair
                            and not legacy_candidates
                            and instant_counts[watched_at] == 1
                            and _relocate_own_play(
                                user,
                                media_id,
                                source,
                                season,
                                episode_number,
                                watched_at,
                                metadata_by_season[season_number],
                            )
                        ):
                            relocated += 1
                            outcomes[client_event_id] = "already_satisfied"
                            continue
                        if legacy_candidates:
                            legacy = legacy_candidates.pop(0)
                            if legacy.watch_operation_id is None:
                                # This is identity adoption for an already-existing
                                # exact timestamp event. Keep it local: Episode.save()
                                # performs provider-backed completion reconciliation,
                                # which would turn one batch fetch into an N+1 path.
                                updated = Episode.objects.filter(
                                    pk=legacy.pk,
                                    watch_operation_id__isnull=True,
                                ).update(watch_operation_id=client_event_id)
                                if updated:
                                    legacy.watch_operation_id = client_event_id
                                else:
                                    claimed = Episode.objects.filter(pk=legacy.pk).only("watch_operation_id").first()
                                    if claimed is None or claimed.watch_operation_id != client_event_id:
                                        if conflicts == "item":
                                            outcomes[client_event_id] = "conflict"
                                            continue
                                        late_conflict = True
                                        break
                            outcomes[client_event_id] = "already_satisfied"
                            continue

                        episode_item = season.get_episode_item(
                            episode_number,
                            season_metadata=metadata_by_season[season_number],
                        )
                        result = create_episode_watch(
                            season,
                            episode_item,
                            watched_at,
                            watch_operation_id=client_event_id,
                            operation_prechecked=True,
                        )
                        outcomes[client_event_id] = "created" if result.created else "already_satisfied"
                        created_any = created_any or result.created
                        if result.created:
                            created_days.add(watched_at)
                break
            except OperationalError as error:
                if "locked" not in str(error).lower():
                    logger.exception("CineTrack episode ensure failed media_id=%s", media_id)
                    raise EpisodeEnsureError(
                        MSG_ENSURE_FAILED,
                        HTTP.INTERNAL_SERVER_ERROR,
                        kind="error",
                        partial=settled,
                    ) from None
                if attempt == len(DB_LOCK_BACKOFF_SECONDS):
                    logger.warning("CineTrack episode ensure: database busy media_id=%s", media_id)
                    raise EpisodeEnsureError(
                        MSG_DB_BUSY,
                        HTTP.SERVICE_UNAVAILABLE,
                        headers={"Retry-After": str(DB_BUSY_RETRY_AFTER_SECONDS)},
                        kind="busy",
                        partial=settled,
                    ) from None
                time.sleep(DB_LOCK_BACKOFF_SECONDS[attempt])
            except Exception:
                logger.exception("CineTrack episode ensure failed media_id=%s", media_id)
                raise EpisodeEnsureError(
                    MSG_ENSURE_FAILED,
                    HTTP.INTERNAL_SERVER_ERROR,
                    kind="error",
                    partial=settled,
                ) from None

        if late_conflict:
            raise EpisodeEnsureError(
                MSG_EVENT_RACE,
                HTTP.CONFLICT,
                kind="conflict",
            )
        if created_any:
            # Plays are saved raw (no provider lookup), which also skips the
            # Episode signals; refresh history days, the history index and
            # home rows once for the whole request instead.
            from app.signals import invalidate_episode_history_for_user

            invalidate_episode_history_for_user(user.id, created_days)

    if relocated:
        logger.info("CineTrack repair moved %d episode play(s) media_id=%s", relocated, media_id)
    _remember_translations(
        source,
        media_id,
        {
            (event[0], event[1]): stored[event[3]]
            for event in parsed
            if event[3] in stored and outcomes.get(event[3]) in {"created", "already_satisfied"}
        },
    )
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if elapsed_ms >= SLOW_EPISODE_ENSURE_MS:
        logger.warning(
            "CineTrack episode ensure slow media_id=%s events=%d total_ms=%d %s",
            media_id,
            len(parsed),
            elapsed_ms,
            " ".join(f"{stage}={ms}" for stage, ms in timings.items()),
        )
    return EpisodeEnsureResult(outcomes, stored, reasons, titles)


class CineTrackBootstrapMoviesEnsureView(drf_views.APIView):
    """Ensure a bounded batch of movie state without provider I/O per item."""

    @extend_schema(
        request=CineTrackMoviesEnsureRequestSerializer,
        responses=BOOTSTRAP_RESPONSES,
    )
    @batched_activity()
    def post(self, request):
        """Ensure a batch of movies exists for the user."""
        raw_entries = request.data.get("movies")
        if not isinstance(raw_entries, list) or not raw_entries:
            return Response({"detail": "movies must be a non-empty list."}, status=HTTP.BAD_REQUEST)
        if len(raw_entries) > MAX_BOOTSTRAP_ITEMS:
            return Response({"detail": f"movies must contain at most {MAX_BOOTSTRAP_ITEMS} entries."}, status=HTTP.BAD_REQUEST)

        parsed = []
        seen_events = set()
        for index, entry in enumerate(raw_entries):
            if not isinstance(entry, dict):
                return Response({"detail": f"movies[{index}] must be an object."}, status=HTTP.BAD_REQUEST)
            source = str(entry.get("source") or "").strip()
            media_id = str(entry.get("media_id") or "").strip()
            if not source or not media_id or not check_source_type(MediaTypes.MOVIE.value, source):
                return Response({"detail": f"movies[{index}] has invalid source or media_id."}, status=HTTP.BAD_REQUEST)
            desired_status = _parse_status(entry.get("status"))
            if desired_status is None:
                return Response({"detail": f"movies[{index}].status is invalid."}, status=HTTP.BAD_REQUEST)
            title = str(entry.get("title") or f"CineTrack movie {media_id}").strip()
            watched_at = external_id = None
            watch = entry.get("watch")
            if watch is not None:
                if not isinstance(watch, dict):
                    return Response({"detail": f"movies[{index}].watch is invalid."}, status=HTTP.BAD_REQUEST)
                external_id = str(watch.get("client_event_id") or "").strip()
                try:
                    watched_at = try_parse_datetime_input(watch.get("watched_at"))
                except (TypeError, ValueError):
                    watched_at = None
                if not external_id or watched_at is None:
                    return Response({"detail": f"movies[{index}].watch requires watched_at and client_event_id."}, status=HTTP.BAD_REQUEST)
                event_key = (source, media_id, external_id)
                if event_key in seen_events:
                    return Response({"detail": "movie client_event_id values must be unique per movie in one request."}, status=HTTP.BAD_REQUEST)
                seen_events.add(event_key)
            parsed.append({
                "source": source,
                "media_id": media_id,
                "title": title,
                "image": entry.get("image") or "",
                "status": desired_status,
                "watched_at": watched_at,
                "external_id": external_id,
            })

        results = []
        outcomes = ensure_movie_entries(request.user, parsed)
        for entry, outcome in zip(parsed, outcomes, strict=True):
            results.append({
                "source": entry["source"],
                "media_id": entry["media_id"],
                "status": outcome.outcome,
            })

        return Response({"results": results}, status=HTTP.OK)


class CineTrackBootstrapShowsEnsureView(drf_views.APIView):
    """Ensure show library state without manufacturing episode history."""

    @extend_schema(
        request=CineTrackShowsEnsureRequestSerializer,
        responses=BOOTSTRAP_RESPONSES,
    )
    @batched_activity()
    def post(self, request):
        """Ensure a batch of shows exists for the user."""
        raw_entries = request.data.get("shows")
        if not isinstance(raw_entries, list) or not raw_entries:
            return Response({"detail": "shows must be a non-empty list."}, status=HTTP.BAD_REQUEST)
        if len(raw_entries) > MAX_BOOTSTRAP_ITEMS:
            return Response({"detail": f"shows must contain at most {MAX_BOOTSTRAP_ITEMS} entries."}, status=HTTP.BAD_REQUEST)

        parsed = []
        for index, entry in enumerate(raw_entries):
            if not isinstance(entry, dict):
                return Response({"detail": f"shows[{index}] must be an object."}, status=HTTP.BAD_REQUEST)
            source = str(entry.get("source") or "").strip()
            media_id = str(entry.get("media_id") or "").strip()
            if not source or not media_id or not check_source_type(MediaTypes.TV.value, source):
                return Response({"detail": f"shows[{index}] has invalid source or media_id."}, status=HTTP.BAD_REQUEST)
            desired_status = _parse_status(entry.get("status"))
            if desired_status is None:
                return Response({"detail": f"shows[{index}].status is invalid."}, status=HTTP.BAD_REQUEST)
            parsed.append({
                "source": source,
                "media_id": media_id,
                "title": str(entry.get("title") or f"CineTrack show {media_id}").strip(),
                "image": entry.get("image") or "",
                "status": desired_status,
            })

        results = []
        outcomes = ensure_show_entries(request.user, parsed)
        for entry, outcome in zip(parsed, outcomes, strict=True):
            results.append({
                "source": entry["source"],
                "media_id": entry["media_id"],
                "status": "created" if outcome.changed else "already_satisfied",
            })

        return Response({"results": results}, status=HTTP.OK)


class MediaEpisodeEnsureView(drf_views.APIView):
    """Ensure exact episode-watch events with one metadata fetch per batch."""

    @extend_schema(
        parameters=[MEDIA_TYPE_TV_ONLY_PARAM],
        request=CineTrackEpisodeEnsureRequestSerializer,
        responses=BOOTSTRAP_RESPONSES,
    )
    def post(self, request, media_type, source, media_id):
        """Ensure a batch of episode watch events exists for the user."""
        # Token-authenticated API requests are authenticated after the
        # middleware that scopes provider credentials, so personal keys
        # (for example a user's own TVDB key) are bound here.
        with credentials.current_user_scope(request.user):
            return self._ensure(request, media_type, source, media_id)

    def _ensure(self, request, media_type, source, media_id):
        if media_type != MediaTypes.TV.value:
            return Response({"detail": "Episodes are supported only for 'tv' media type."}, status=HTTP.BAD_REQUEST)
        if not check_source_type(media_type, source):
            return Response({"detail": f"Cannot query `{source}` for `{media_type}` media type"}, status=HTTP.BAD_REQUEST)

        raw_events = request.data.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            return Response({"detail": "events must be a non-empty list."}, status=HTTP.BAD_REQUEST)
        if len(raw_events) > MAX_EPISODE_EVENTS:
            return Response({"detail": f"events must contain at most {MAX_EPISODE_EVENTS} entries."}, status=HTTP.BAD_REQUEST)

        parsed = []
        for index, event in enumerate(raw_events):
            if not isinstance(event, dict):
                return Response({"detail": f"events[{index}] must be an object."}, status=HTTP.BAD_REQUEST)
            try:
                season_number = int(event["season_number"])
                episode_number = int(event["episode_number"])
                client_event_id = UUID(str(event["client_event_id"]))
                watched_at = try_parse_datetime_input(event["watched_at"])
            except (KeyError, TypeError, ValueError):
                return Response({"detail": f"events[{index}] has invalid season_number, episode_number, watched_at, or client_event_id."}, status=HTTP.BAD_REQUEST)
            # Season 0 holds a show's specials, which Floppy tracks like any season.
            if season_number < 0 or episode_number < 1 or watched_at is None:
                return Response({"detail": f"events[{index}] has invalid coordinates or watched_at."}, status=HTTP.BAD_REQUEST)
            parsed.append((season_number, episode_number, watched_at, client_event_id))

        if len({event[3] for event in parsed}) != len(parsed):
            return Response({"detail": "client_event_id values must be unique per request."}, status=HTTP.BAD_REQUEST)

        try:
            ensured = ensure_episode_events(
                request.user,
                source,
                media_id,
                parsed,
                repair=request.data.get("repair_coordinates") is True,
                library_media_type=str(request.data.get("library_media_type") or "").strip(),
            )
        except EpisodeEnsureError as error:
            return Response({"detail": error.detail}, status=error.status, headers=error.headers)
        outcomes, stored, reasons, titles = ensured

        results = []
        for season_number, episode_number, _watched_at, client_event_id in parsed:
            result = {
                "client_event_id": str(client_event_id),
                "season_number": season_number,
                "episode_number": episode_number,
                "status": outcomes[client_event_id],
            }
            if client_event_id in stored and outcomes[client_event_id] in {"created", "already_satisfied"}:
                result["stored_season_number"], result["stored_episode_number"] = stored[client_event_id]
            if outcomes[client_event_id] in {"not_found", "metadata_unavailable"}:
                result["reason"] = reasons.get(client_event_id, "no_tmdb_episode")
                if client_event_id in titles:
                    result["title"] = titles[client_event_id]
            results.append(result)
        return Response({"results": results}, status=HTTP.OK)


class MediaEpisodeTranslateView(drf_views.APIView):
    """Translate episode coordinates between a tracker's numbering and TMDB's.

    Read-only: it resolves exactly like :func:`ensure_episode_events` but never
    creates or changes a play, season or episode row.
    """

    @extend_schema(
        parameters=[MEDIA_TYPE_TV_ONLY_PARAM],
        request=CineTrackEpisodeTranslateRequestSerializer,
        responses={
            200: CineTrackEpisodeTranslateResponseSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Malformed request."),
            404: OpenApiResponse(DetailErrorSerializer, description="Episode metadata could not be fetched."),
        },
    )
    def post(self, request, media_type, source, media_id):
        """Translate episode coordinates between providers."""
        with credentials.current_user_scope(request.user):
            return self._translate(request, media_type, source, media_id)

    def _translate(self, request, media_type, source, media_id):
        if media_type != MediaTypes.TV.value:
            return Response({"detail": "Episodes are supported only for 'tv' media type."}, status=HTTP.BAD_REQUEST)
        if not check_source_type(media_type, source):
            return Response({"detail": f"Cannot query `{source}` for `{media_type}` media type"}, status=HTTP.BAD_REQUEST)
        origin = request.data.get("from")
        if origin not in {"tracker", "tmdb"}:
            return Response({"detail": "from must be 'tracker' or 'tmdb'."}, status=HTTP.BAD_REQUEST)
        raw_episodes = request.data.get("episodes")
        if not isinstance(raw_episodes, list) or not raw_episodes:
            return Response({"detail": "episodes must be a non-empty list."}, status=HTTP.BAD_REQUEST)
        if len(raw_episodes) > MAX_TRANSLATE_EPISODES:
            return Response({"detail": f"episodes must contain at most {MAX_TRANSLATE_EPISODES} entries."}, status=HTTP.BAD_REQUEST)
        events = []
        for index, entry in enumerate(raw_episodes):
            if not isinstance(entry, dict):
                return Response({"detail": f"episodes[{index}] must be an object."}, status=HTTP.BAD_REQUEST)
            season_number, episode_number = entry.get("season"), entry.get("episode")
            if (
                not isinstance(season_number, int) or isinstance(season_number, bool)
                or not isinstance(episode_number, int) or isinstance(episode_number, bool)
                or season_number < 0 or episode_number < 1
            ):
                return Response({"detail": f"episodes[{index}] has invalid season or episode."}, status=HTTP.BAD_REQUEST)
            watched_at = None
            if entry.get("watched_at") is not None:
                try:
                    watched_at = try_parse_datetime_input(entry["watched_at"])
                except (TypeError, ValueError):
                    watched_at = None
                if watched_at is None:
                    return Response({"detail": f"episodes[{index}].watched_at is invalid."}, status=HTTP.BAD_REQUEST)
            events.append((season_number, episode_number, watched_at, index))

        try:
            results = _translate_coordinates(request.user, source, media_id, events, from_tracker=origin == "tracker")
        except EpisodeEnsureError as error:
            return Response({"detail": error.detail}, status=error.status, headers=error.headers)
        return Response({"results": results}, status=HTTP.OK)


def _coordinate_payload(coordinate):
    return None if coordinate is None else {"season": coordinate[0], "episode": coordinate[1]}


def _resolve_tracker_coordinates(user, source, media_id, events):
    """Resolve tracker coordinates; remembered translations skip the heavy stages."""
    memo = _remembered_translations(source, media_id)
    remembered = {
        event[3]: memo[(event[0], event[1])]
        for event in events
        if memo.get((event[0], event[1])) not in {None, (event[0], event[1])}
    }
    # A remembered target is looked up directly: no absolute walk and no TVDB
    # fetch, unless it no longer exists on TMDB.
    first = [(*remembered[event[3]], event[2], event[3]) if event[3] in remembered else event for event in events]
    resolution = resolve_episode_coordinates(user, source, media_id, first)
    if resolution.show_unknown or not remembered:
        return resolution
    direct = {item[3] for item in resolution.resolvable if item[3] not in resolution.stored}
    retry = [event for event in events if event[3] in remembered and event[3] not in direct]
    retry_keys = {event[3] for event in retry}
    outcomes = {key: value for key, value in resolution.outcomes.items() if key not in retry_keys}
    reasons = {key: value for key, value in resolution.reasons.items() if key not in retry_keys}
    stored = {key: value for key, value in resolution.stored.items() if key not in retry_keys}
    resolvable = [item for item in resolution.resolvable if item[3] not in retry_keys]
    metadata_by_season = dict(resolution.metadata_by_season)
    # Remembered events that resolved directly sit at their target; report the
    # translation from the submitted coordinate.
    for item in resolvable:
        if item[3] in remembered:
            stored[item[3]] = (item[0], item[1])
    if retry:
        again = resolve_episode_coordinates(user, source, media_id, retry)
        if again.show_unknown:
            return again
        resolvable.extend(again.resolvable)
        stored.update(again.stored)
        outcomes.update(again.outcomes)
        reasons.update(again.reasons)
        for season_number, season_metadata in again.metadata_by_season.items():
            metadata_by_season.setdefault(season_number, season_metadata)
    return CoordinateResolution(
        resolvable,
        stored,
        outcomes,
        reasons,
        resolution.titles,
        metadata_by_season,
        resolution.combined_metadata,
    )


def _resolve_tmdb_coordinates(media_id, source, events):
    """Check coordinates against TMDB as listed: no translation at all."""
    outcomes = {}
    reasons = {}
    metadata_by_season = {}
    resolvable = []
    season_numbers = sorted({event[0] for event in events})
    try:
        combined_metadata = services.get_media_metadata("tv_with_seasons", media_id, source, season_numbers)
    except services.ProviderAPIError as error:
        if error.status_code != HTTP.NOT_FOUND:
            raise
        return CoordinateResolution([], {}, {}, {}, {}, {}, None, show_unknown=True)
    for season_number in season_numbers:
        season_metadata = combined_metadata.get(f"season/{season_number}")
        if not isinstance(season_metadata, dict) and len(season_numbers) == 1 and isinstance(combined_metadata.get("episodes"), list):
            season_metadata = combined_metadata
        if isinstance(season_metadata, dict):
            season_metadata.setdefault("_tvdb_episode_image_map", {})
            metadata_by_season[season_number] = season_metadata
    listed_seasons = _listed_season_numbers(combined_metadata)
    for event in events:
        season_number, episode_number, _watched_at, key = event
        if season_number not in metadata_by_season:
            if listed_seasons and season_number not in listed_seasons:
                outcomes[key], reasons[key] = "not_found", "unknown_to_provider"
            else:
                outcomes[key], reasons[key] = "metadata_unavailable", "season_metadata_missing"
            continue
        try:
            resolve_episode_coordinate(
                media_id,
                source,
                season_number,
                episode_number,
                season_metadata=metadata_by_season[season_number],
            )
        except InvalidEpisodeCoordinateError:
            outcomes[key], reasons[key] = "not_found", "unknown_to_provider"
        except EpisodeMetadataUnavailableError:
            outcomes[key], reasons[key] = "metadata_unavailable", "season_metadata_missing"
        else:
            resolvable.append(event)
    return CoordinateResolution(resolvable, {}, outcomes, reasons, {}, metadata_by_season, combined_metadata)


def _translate_coordinates(user, source, media_id, events, *, from_tracker):
    """Return the translate view's result rows, one per event, in order."""
    try:
        if from_tracker:
            resolution = _resolve_tracker_coordinates(user, source, media_id, events)
        else:
            resolution = _resolve_tmdb_coordinates(media_id, source, events)
    except (_CoordinateMetadataError, services.ProviderAPIError):
        raise EpisodeEnsureError(MSG_RESOLVE_FAILED, HTTP.NOT_FOUND, kind="metadata") from None
    except Exception:
        logger.exception("CineTrack episode translate failed media_id=%s", media_id)
        raise EpisodeEnsureError(MSG_RESOLVE_FAILED, HTTP.NOT_FOUND, kind="metadata") from None

    if resolution.show_unknown:
        return [
            {
                "season": event[0], "episode": event[1], "status": "not_found",
                "tmdb": None, "absolute": None, "tvdb": None, "reason": "unknown_to_provider",
            }
            for event in events
        ]
    placed = {item[3]: (item[0], item[1]) for item in resolution.resolvable}
    if from_tracker:
        # Remember what was learned, exactly as a later ensure would.
        _remember_translations(
            source,
            media_id,
            {
                (event[0], event[1]): placed[event[3]]
                for event in events
                if event[3] in placed and placed[event[3]] != (event[0], event[1])
            },
        )
    metadata = resolution.combined_metadata
    metadata_by_season = resolution.metadata_by_season
    tvdb_catalogue = _cached_tvdb_catalogue(metadata, metadata_by_season)
    tmdb_episodes = _tmdb_episode_rows(metadata_by_season) if tvdb_catalogue else []
    absolute_seasons = _absolutely_numbered_seasons(metadata_by_season)
    results = []
    for season_number, episode_number, _watched_at, key in events:
        target = placed.get(key)
        if target is None:
            results.append({
                "season": season_number, "episode": episode_number,
                "status": resolution.outcomes.get(key, "not_found"),
                "tmdb": None, "absolute": None, "tvdb": None,
                "reason": resolution.reasons.get(key, "no_tmdb_episode"),
            })
            continue
        results.append({
            "season": season_number,
            "episode": episode_number,
            "status": "same" if target == (season_number, episode_number) else "translated",
            "tmdb": _coordinate_payload(target),
            "absolute": _absolute_number(metadata, metadata_by_season, absolute_seasons, target),
            "tvdb": _coordinate_payload(
                _tvdb_coordinate(tvdb_catalogue, tmdb_episodes, target, (season_number, episode_number)),
            ),
            "reason": None,
        })
    return results


def _tmdb_episode_rows(metadata_by_season):
    return [
        {
            "season_number": season_number,
            "episode_number": int(row["episode_number"]),
            "air_date": _parse_air_date(row.get("air_date")),
            "title": _normalized_title(row.get("name") or row.get("title")),
        }
        for season_number, season_metadata in metadata_by_season.items()
        for row in season_metadata.get("episodes") or []
        if isinstance(row, dict) and row.get("episode_number") is not None
    ]


def _absolute_number(metadata, metadata_by_season, absolute_seasons, target):
    """Absolute number of a TMDB coordinate in a regular season, else None."""
    season_number, episode_number = target
    if season_number < 1:
        return None
    if season_number in absolute_seasons:
        return episode_number
    declared = {}
    for season in (metadata.get("related") or {}).get("seasons") or []:
        if isinstance(season, dict):
            try:
                declared[int(season.get("season_number"))] = int(season.get("episode_count") or 0)
            except (TypeError, ValueError):
                continue
    before = 0
    for number in sorted({*declared, *metadata_by_season}):
        if number < 1 or number >= season_number:
            continue
        loaded = (metadata_by_season.get(number) or {}).get("episodes")
        before += len(loaded) if isinstance(loaded, list) else declared.get(number, 0)
    return before + episode_number


def _cached_tvdb_catalogue(metadata, metadata_by_season):
    """Return the show's default TVDB catalogue if already cached; never fetch it."""
    if not isinstance(metadata, dict):
        return {}
    # A partial TMDB listing could make an identity match look unique by accident.
    if not _listed_season_numbers(metadata) <= set(metadata_by_season):
        return {}
    try:
        external_ids = metadata.get("provider_external_ids") or {}
        tvdb_id = str(metadata.get("tvdb_id") or external_ids.get("tvdb_id") or "").strip()
        if not tvdb_id:
            return {}
        cached = cache.get(f"cinetrack_tvdb_catalogue_v2_{tvdb_id}_default_{tvdb._preferred_language_code()}")
    except Exception:
        return {}
    return (cached or {}).get("catalogue") or {}


def _tvdb_coordinate(catalogue, tmdb_episodes, target, submitted):
    """TVDB official-order coordinate of a resolved TMDB episode, if provable."""
    if not catalogue:
        return None
    for candidate in dict.fromkeys([submitted, target]):
        tvdb_episode = catalogue.get(candidate)
        if tvdb_episode is None:
            continue
        match = _match_tmdb_episode(tvdb_episode, tmdb_episodes, _day_rank(catalogue, tvdb_episode))
        if match is not None and (match["season_number"], match["episode_number"]) == target:
            return candidate
    return None


def _relocate_own_play(user, media_id, source, season, episode_number, watched_at, season_metadata):
    """Move this event's own play onto (season, episode_number) if it is elsewhere.

    The play is this event's only when it is the show's single play at that
    exact instant and CineTrack wrote it (it carries an operation id). Plays
    sharing an instant (bulk-marked seasons) are never moved. Returns whether
    a play was moved; its time and operation id are kept.
    """
    plays = list(
        Episode.objects.filter(
            related_season__user=user,
            related_season__item__media_id=str(media_id),
            related_season__item__source=source,
            end_date=watched_at,
        ).select_related("related_season__item", "item")[:2],
    )
    if len(plays) != 1:
        return False
    play = plays[0]
    if not play.watch_operation_id:
        return False
    if play.related_season_id == season.id and play.item.episode_number == episode_number:
        return False
    operation_id = play.watch_operation_id
    target_item = season.get_episode_item(episode_number, season_metadata=season_metadata)
    play.delete()
    create_episode_watch(season, target_item, watched_at, watch_operation_id=operation_id, operation_prechecked=True)
    return True


def _uses_absolute_numbering(metadata):
    """Japanese shows (anime), which trackers number continuously across seasons."""
    if not isinstance(metadata, dict):
        return False
    # Genre and country names follow the server's TMDB language ("Animazione",
    # "Giappone"); spoken languages are always TMDB's English names.
    details = metadata.get("details") or {}
    return "Japanese" in (details.get("languages") or [])


def _absolute_targets(metadata, season_one, events):
    """Map season-1 absolute episode numbers onto TMDB's regular seasons.

    Only for anime, only when TMDB's season-1 summary count matches its actual
    season-1 episode list (so the counting basis is consistent), and only for
    numbers that fall inside the regular seasons TMDB lists.
    """
    if not events or not _uses_absolute_numbering(metadata) or not isinstance(season_one, dict):
        return {}
    counts = []
    for season in (metadata.get("related") or {}).get("seasons") or []:
        if not isinstance(season, dict):
            continue
        try:
            number = int(season.get("season_number"))
            count = int(season.get("episode_count") or 0)
        except (TypeError, ValueError):
            continue
        if number >= 1 and count > 0:
            counts.append((number, count))
    counts.sort()
    season_one_episodes = season_one.get("episodes")
    if not counts or counts[0][0] != 1 or not isinstance(season_one_episodes, list):
        return {}
    if counts[0][1] != len(season_one_episodes):
        return {}
    targets = {}
    for _season, episode_number, _watched_at, client_event_id in events:
        remaining = episode_number
        for number, count in counts:
            if remaining <= count:
                targets[client_event_id] = (number, remaining)
                break
            remaining -= count
    return targets


_PART_MARKER = re.compile(r"\(\s*(?:part\s*)?\d+\s*\)|\b(?:part|pt)\.?\s*(?:\d+|one|two|three|i{1,3})\b")
_GENERIC_TITLE = re.compile(r"^(?:episode|ep)\s*\d+$")


def _normalized_title(value):
    title = _PART_MARKER.sub(" ", str(value or "").lower())
    return " ".join(re.sub(r"[^\w]+", " ", title).split())


def _titles_match(left, right):
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    if len(shorter) >= 4 and longer.startswith(shorter):  # noqa: PLR2004
        return True
    # A title inside a longer one as whole words, e.g. TMDB's "Game of
    # Thrones: The Last Watch" for TVDB's "The Last Watch".
    return len(shorter) >= 8 and f" {shorter} " in f" {longer} "  # noqa: PLR2004


def _parse_air_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _match_tmdb_episode(tvdb_episode, tmdb_episodes, day_rank=None):
    """Pick the one TMDB episode that is the same broadcast, or None.

    Same air date decides alone when it is unique (a merged two-parter's
    halves air together); otherwise the title must also agree. When titles
    cannot tell apart several episodes aired the same day (anime double
    episodes, titles in different languages) and TVDB lists exactly as many
    that day, their order within the day pairs them up; ``day_rank`` is
    (position, count) of this episode among TVDB's episodes of that day. A
    unique, non-generic exact title is the last resort (specials with sloppy
    dates).
    """
    title = _normalized_title(tvdb_episode.get("title"))

    def titled(rows):
        return [row for row in rows if _titles_match(title, row["title"])]

    aired = _parse_air_date(tvdb_episode.get("air_date"))
    if aired is not None:
        same_day = [row for row in tmdb_episodes if row["air_date"] == aired]
        if len(same_day) == 1:
            return same_day[0]
        if len(titled(same_day)) == 1:
            return titled(same_day)[0]
        if day_rank is not None and len(same_day) == day_rank[1] > 1:
            ordered = sorted(same_day, key=lambda row: (row["season_number"], row["episode_number"]))
            return ordered[day_rank[0]]
        if not same_day:
            near = [
                row for row in tmdb_episodes
                if row["air_date"] is not None and abs((row["air_date"] - aired).days) <= 1
            ]
            if len(titled(near)) == 1:
                return titled(near)[0]
    if title and not _GENERIC_TITLE.match(title):
        exact = [row for row in tmdb_episodes if row["title"] == title]
        if len(exact) == 1:
            return exact[0]
    return None


# TVDB episode lists rarely change; one that misses an episode is refetched
# once it is older than an hour, so newly aired episodes are still found.
TVDB_CATALOGUE_CACHE_SECONDS = 7 * 24 * 60 * 60
TVDB_CATALOGUE_FRESH_SECONDS = 60 * 60
TRANSLATION_CACHE_SECONDS = 30 * 24 * 60 * 60


def _translation_cache_key(source, media_id):
    return f"cinetrack_episode_translations_v1_{source}_{media_id}"


def _remembered_translations(source, media_id):
    """Return {(sent season, sent episode): (stored season, stored episode)}."""
    return cache.get(_translation_cache_key(source, media_id)) or {}


def _remember_translations(source, media_id, translations):
    """Keep where episodes sent under another numbering were stored.

    Only a lookup hint: an event is matched through it solely when the user's
    play is stored there at the exact same instant.
    """
    if not translations:
        return
    known = _remembered_translations(source, media_id)
    if all(known.get(sent) == target for sent, target in translations.items()):
        return
    cache.set(_translation_cache_key(source, media_id), {**known, **translations}, TRANSLATION_CACHE_SECONDS)


def _load_listed_seasons(media_id, source, metadata, metadata_by_season):
    """Add every season TMDB lists for the show to ``metadata_by_season``."""
    missing = sorted(_listed_season_numbers(metadata) - set(metadata_by_season))
    if not missing:
        return
    extra = services.get_media_metadata("tv_with_seasons", media_id, source, missing)
    for season_number in missing:
        season_metadata = extra.get(f"season/{season_number}")
        if isinstance(season_metadata, dict):
            season_metadata.setdefault("_tvdb_episode_image_map", {})
            metadata_by_season[season_number] = season_metadata


def _absolutely_numbered_seasons(metadata_by_season):
    """Return {season: episode numbers} for seasons that keep absolute numbers.

    Only regular seasons after the first whose numbering does not restart at 1.
    """
    seasons = {}
    for season_number, season_metadata in metadata_by_season.items():
        if season_number < 2:  # noqa: PLR2004
            continue
        numbers = {
            int(row["episode_number"])
            for row in season_metadata.get("episodes") or []
            if isinstance(row, dict) and row.get("episode_number") is not None
        }
        if numbers and min(numbers) > 1:
            seasons[season_number] = numbers
    return seasons


def _absolute_number_targets(media_id, source, metadata_by_season, events):
    """Map absolute numbers to the one absolutely numbered season listing them."""
    seasons = _absolutely_numbered_seasons(metadata_by_season)
    targets = {}
    for _season, episode_number, _watched_at, client_event_id in events:
        holders = [season for season, numbers in seasons.items() if episode_number in numbers]
        if len(holders) != 1:
            continue
        target = (holders[0], episode_number)
        try:
            resolve_episode_coordinate(
                media_id,
                source,
                target[0],
                target[1],
                season_metadata=metadata_by_season[target[0]],
            )
        except (InvalidEpisodeCoordinateError, EpisodeMetadataUnavailableError):
            continue
        targets[client_event_id] = target
    return targets


def _day_rank(catalogue, tvdb_episode):
    """(position, count) of an episode among the catalogue's episodes that aired the same day."""
    aired = tvdb_episode.get("air_date")
    if not aired:
        return None
    same_day = sorted(coordinate for coordinate, row in catalogue.items() if row.get("air_date") == aired)
    position = next(
        (index for index, coordinate in enumerate(same_day) if catalogue[coordinate] is tvdb_episode),
        None,
    )
    return None if position is None else (position, len(same_day))


def _listed_season_numbers(metadata):
    """Season numbers TMDB lists for the show (empty when unknown)."""
    numbers = set()
    if not isinstance(metadata, dict):
        return numbers
    for season in (metadata.get("related") or {}).get("seasons") or []:
        if isinstance(season, dict) and str(season.get("season_number", "")).isdigit():
            numbers.add(int(season["season_number"]))
    return numbers


def _in_tvdb(event, catalogue, absolute):
    """Whether TVDB lists the event's coordinate (season 1 also absolutely)."""
    return (event[0], event[1]) in catalogue or (event[0] == 1 and (1, event[1]) in absolute)


def _tvdb_catalogues(tvdb_id, events, user, max_age=None):
    """Return the default catalogue and, when season 1 needs it, the absolute one."""
    catalogue = _tvdb_catalogue(tvdb_id, "default", user, max_age=max_age)
    # Trackers number anime continuously in one season; TVDB's absolute
    # order holds exactly that numbering.
    if any(event[0] == 1 and (1, event[1]) not in catalogue for event in events):
        absolute = _tvdb_catalogue(tvdb_id, "absolute", user, max_age=max_age)
    else:
        absolute = {}
    return catalogue, absolute


def _tvdb_catalogue(tvdb_id, order, user, max_age=None):
    """Return {(season, number): {"air_date", "title"}} for one TVDB order.

    Coordinates TVDB lists more than once are dropped rather than guessed, and
    an order the series does not have is an empty catalogue. The absolute
    order is keyed (1, absolute number), the way trackers number anime. A
    kept catalogue older than ``max_age`` seconds is fetched again.
    """
    language = tvdb._preferred_language_code()
    cache_key = f"cinetrack_tvdb_catalogue_v2_{tvdb_id}_{order}_{language}"
    cached = cache.get(cache_key)
    if cached is not None and (max_age is None or time.time() - cached["fetched_at"] < max_age):
        return cached["catalogue"]
    rows = []
    path = f"series/{tvdb_id}/episodes/{order}/{language}"
    try:
        for page in range(episode_orders.MAX_PAGES):
            response = tvdb._request(path, params={"page": page}, user=user)
            page_rows = (response.get("data") or {}).get("episodes") or []
            rows.extend(page_rows)
            if not page_rows or not (response.get("links") or {}).get("next"):
                break
    except services.ProviderAPIError as error:
        if error.status_code != HTTP.NOT_FOUND:
            raise
        rows = []
    catalogue = {}
    duplicates = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        season = 1 if order == "absolute" else row.get("seasonNumber")
        number = (row.get("absoluteNumber") or row.get("number")) if order == "absolute" else row.get("number")
        if season is None or not number:
            continue
        coordinate = (int(season), int(number))
        if coordinate in catalogue:
            duplicates.add(coordinate)
        catalogue[coordinate] = {"air_date": row.get("aired"), "title": row.get("name") or ""}
    for coordinate in duplicates:
        catalogue.pop(coordinate, None)
    cache.set(cache_key, {"fetched_at": time.time(), "catalogue": catalogue}, TVDB_CATALOGUE_CACHE_SECONDS)
    return catalogue


def _identity_targets(user, media_id, source, metadata, metadata_by_season, events):
    """Map events TMDB numbers differently onto TMDB episodes via TVDB.

    Returns (targets, unavailable, reasons, titles): targets maps
    client_event_id to a TMDB (season, episode) that Floppy can store;
    unavailable holds events whose lookup failed transiently and should be
    retried later; reasons says why each other event could not be placed and
    titles gives TVDB's title for those TVDB knows. Seasons fetched here are
    added to ``metadata_by_season``.
    """
    event_ids = {event[3] for event in events}
    if not events or source != "tmdb":
        return {}, set(), {}, {}
    if not tvdb.enabled(user):
        return {}, set(), dict.fromkeys(event_ids, "tvdb_not_configured"), {}
    try:
        external_ids = metadata.get("provider_external_ids") or {}
        tvdb_id = (
            str(metadata.get("tvdb_id") or external_ids.get("tvdb_id") or "").strip()
            or tmdb.resolve_tvdb_id_for_tmdb_show(media_id, tv_data=metadata)
        )
        if not tvdb_id:
            return {}, set(), dict.fromkeys(event_ids, "tvdb_id_unknown"), {}
        catalogue, absolute = _tvdb_catalogues(tvdb_id, events, user)
        if any(not _in_tvdb(event, catalogue, absolute) for event in events):
            # A kept list may predate a newly aired episode.
            catalogue, absolute = _tvdb_catalogues(tvdb_id, events, user, max_age=TVDB_CATALOGUE_FRESH_SECONDS)
        _load_listed_seasons(media_id, source, metadata, metadata_by_season)
    except Exception as error:
        logger.warning(
            "CineTrack TVDB episode lookup failed media_id=%s error=%s",
            media_id,
            type(error).__name__,
        )
        return {}, event_ids, dict.fromkeys(event_ids, "tvdb_unavailable"), {}

    tmdb_episodes = []
    for season_number, season_metadata in metadata_by_season.items():
        for row in season_metadata.get("episodes") or []:
            if not isinstance(row, dict) or row.get("episode_number") is None:
                continue
            tmdb_episodes.append({
                "season_number": season_number,
                "episode_number": int(row["episode_number"]),
                "air_date": _parse_air_date(row.get("air_date")),
                "title": _normalized_title(row.get("name") or row.get("title")),
            })

    targets = {}
    reasons = {}
    titles = {}
    for season_number, episode_number, _watched_at, client_event_id in events:
        tvdb_episode = catalogue.get((season_number, episode_number))
        if tvdb_episode is None and season_number == 1:
            tvdb_episode = absolute.get((1, episode_number))
        if tvdb_episode is None:
            reasons[client_event_id] = "not_in_tvdb"
            continue
        source_catalogue = catalogue if tvdb_episode is catalogue.get((season_number, episode_number)) else absolute
        match = _match_tmdb_episode(tvdb_episode, tmdb_episodes, _day_rank(source_catalogue, tvdb_episode))
        if match is None:
            reasons[client_event_id] = "no_unique_tmdb_match"
            titles[client_event_id] = str(tvdb_episode.get("title") or "")[:200]
            continue
        target = (match["season_number"], match["episode_number"])
        try:
            resolve_episode_coordinate(
                media_id,
                source,
                target[0],
                target[1],
                season_metadata=metadata_by_season[target[0]],
            )
        except (InvalidEpisodeCoordinateError, EpisodeMetadataUnavailableError):
            reasons[client_event_id] = "no_unique_tmdb_match"
            titles[client_event_id] = str(tvdb_episode.get("title") or "")[:200]
            continue
        targets[client_event_id] = target
    return targets, set(), reasons, titles


# Scoped-token enforcement keys views by module.ClassName.  Preserve the
# existing public keys so the optimized implementation is a transparent server
# upgrade rather than a new permission surface.
CineTrackBootstrapMoviesEnsureView.__module__ = "api.fork_views_tracking"
CineTrackBootstrapShowsEnsureView.__module__ = "api.fork_views_tracking"
MediaEpisodeEnsureView.__module__ = "api.fork_views_tracking"
MediaEpisodeTranslateView.__module__ = "api.fork_views_tracking"
