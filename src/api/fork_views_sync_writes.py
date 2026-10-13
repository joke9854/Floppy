"""Trakt-style batched sync writes with one outcome per submitted item.

Four POST endpoints (history add, history remove, ratings, status) accept a mixed
batch and answer HTTP 200 with exactly one result per input item. Only a
malformed request (bad shape, limits exceeded, a duplicate client_event_id) is a
400. The write logic is shared with the CineTrack bootstrap endpoints
(``cinetrack_bootstrap_views``): plays are stored at exactly the submitted
instant, never deduplicated by coordinates alone, and a completed status never
creates episode history.
"""

import logging
import time
from collections import Counter, OrderedDict
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from http import HTTPStatus as HTTP  # noqa: N814
from uuid import NAMESPACE_URL, UUID, uuid5

from django.db import OperationalError, transaction
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import cache_utils
from app.models import (
    BasicMedia,
    Episode,
    Item,
    MediaTypes,
    Movie,
    MoviePlay,
    Status,
)
from app.providers import credentials, services
from app.services import metadata_resolution
from app.services.sync_activity import batched_activity

from .cinetrack_bootstrap_views import (
    DB_LOCK_BACKOFF_SECONDS,
    EpisodeEnsureError,
    ensure_episode_events,
    ensure_movie_entries,
    ensure_show_entries,
)
from .contract_serializers import DetailErrorSerializer
from .helpers import apply_episode_score, check_source_type
from .sync_ids import has_resolved_entries, resolve_entry_ids, splice_unresolved

logger = logging.getLogger(__name__)

MAX_SYNC_EVENTS = 500
MAX_SYNC_SHOWS = 50
MAX_SYNC_REMOVALS = 500
MAX_SYNC_RATINGS = 500
MAX_SYNC_STATUS_ITEMS = 200
MAX_CLIENT_EVENT_ID_LENGTH = 255
_SCORE_STEP = Decimal("0.1")
# Opaque client_event_id strings are stored in Episode's UUID column through a
# deterministic name-based UUID; real UUID strings are stored unchanged.
_OPAQUE_ID_NAMESPACE = uuid5(NAMESPACE_URL, "floppy:sync:client_event_id")
_STATUS_BY_NAME = {
    "planning": Status.PLANNING.value,
    "in_progress": Status.IN_PROGRESS.value,
    "paused": Status.PAUSED.value,
    "dropped": Status.DROPPED.value,
    "completed": Status.COMPLETED.value,
}
_WRITTEN = {"created", "already_satisfied"}


class ExternalIdsSerializer(serializers.Serializer):
    """External ids that name an item instead of source + media_id."""

    tmdb = serializers.CharField(required=False)
    imdb = serializers.CharField(required=False)
    tvdb = serializers.CharField(required=False)


class SyncHistoryMovieSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    source = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    media_id = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    ids = ExternalIdsSerializer(required=False)
    watched_at = serializers.DateTimeField()
    client_event_id = serializers.CharField(
        min_length=1, max_length=MAX_CLIENT_EVENT_ID_LENGTH
    )
    title = serializers.CharField(required=False, allow_blank=True)


class SyncHistoryEpisodeSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    source = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    media_id = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    ids = ExternalIdsSerializer(required=False)
    season_number = serializers.IntegerField(min_value=0)
    episode_number = serializers.IntegerField(min_value=1)
    watched_at = serializers.DateTimeField()
    client_event_id = serializers.CharField(
        min_length=1, max_length=MAX_CLIENT_EVENT_ID_LENGTH
    )


class SyncHistoryRequestSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    movies = SyncHistoryMovieSerializer(many=True, required=False)
    episodes = SyncHistoryEpisodeSerializer(many=True, required=False)


class SyncHistoryResultSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    client_event_id = serializers.CharField()
    type = serializers.ChoiceField(choices=("movie", "episode"))
    outcome = serializers.ChoiceField(
        choices=(
            "created",
            "already_satisfied",
            "not_found",
            "metadata_unavailable",
            "conflict",
            "failed",
        ),
    )
    stored_season_number = serializers.IntegerField(required=False)
    stored_episode_number = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    ids = ExternalIdsSerializer(
        required=False, help_text="The ids of an entry they did not match."
    )


class SyncHistoryResponseSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    results = SyncHistoryResultSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())


class SyncRemoveMovieSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    source = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    media_id = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    ids = ExternalIdsSerializer(required=False)
    client_event_id = serializers.CharField(
        required=False, max_length=MAX_CLIENT_EVENT_ID_LENGTH
    )
    watched_at = serializers.DateTimeField(required=False)
    all = serializers.BooleanField(required=False)


class SyncRemoveEpisodeSerializer(SyncRemoveMovieSerializer):
    """Request or response shape for the sync write endpoints."""

    season_number = serializers.IntegerField(min_value=0)
    episode_number = serializers.IntegerField(min_value=1)


class SyncRemoveRequestSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    movies = SyncRemoveMovieSerializer(many=True, required=False)
    episodes = SyncRemoveEpisodeSerializer(many=True, required=False)


class SyncItemResultSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    type = serializers.ChoiceField(choices=("movie", "show", "episode"))
    source = serializers.CharField()
    media_id = serializers.CharField()
    season_number = serializers.IntegerField(required=False)
    episode_number = serializers.IntegerField(required=False)
    client_event_id = serializers.CharField(required=False)
    outcome = serializers.CharField()
    removed_count = serializers.IntegerField(required=False)
    reason = serializers.CharField(required=False)
    ids = ExternalIdsSerializer(
        required=False, help_text="The ids of an entry they did not match."
    )


class SyncItemsResponseSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    results = SyncItemResultSerializer(many=True)
    counts = serializers.DictField(child=serializers.IntegerField())


class SyncRatingMediaSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    source = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    media_id = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    ids = ExternalIdsSerializer(required=False)
    score = serializers.DecimalField(max_digits=3, decimal_places=1, allow_null=True)


class SyncRatingEpisodeSerializer(SyncRatingMediaSerializer):
    """Request or response shape for the sync write endpoints."""

    season_number = serializers.IntegerField(min_value=0)
    episode_number = serializers.IntegerField(min_value=1)


class SyncRatingsRequestSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    movies = SyncRatingMediaSerializer(many=True, required=False)
    shows = SyncRatingMediaSerializer(many=True, required=False)
    episodes = SyncRatingEpisodeSerializer(many=True, required=False)


class SyncStatusItemSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    source = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    media_id = serializers.CharField(
        required=False, help_text="Required unless ids is given."
    )
    ids = ExternalIdsSerializer(required=False)
    status = serializers.ChoiceField(choices=tuple(_STATUS_BY_NAME))
    title = serializers.CharField(required=False, allow_blank=True)


class SyncStatusRequestSerializer(serializers.Serializer):
    """Request or response shape for the sync write endpoints."""

    movies = SyncStatusItemSerializer(many=True, required=False)
    shows = SyncStatusItemSerializer(many=True, required=False)


_SYNC_RESPONSES = {
    400: OpenApiResponse(
        DetailErrorSerializer,
        description="Malformed request or limits exceeded; nothing was written.",
    ),
}


class SyncRequestError(Exception):
    """A malformed request, answered as HTTP 400."""


def _bad(detail):
    raise SyncRequestError(detail)


def _list_field(data, key):
    value = data.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        _bad(f"{key} must be a list.")
    return value


def _entry(raw, label, index):
    if not isinstance(raw, dict):
        _bad(f"{label}[{index}] must be an object.")
    return raw


def _media_ref(raw, label, index, media_type):
    source = str(raw.get("source") or "").strip()
    media_id = str(raw.get("media_id") or "").strip()
    if not source or not media_id or not check_source_type(media_type, source):
        _bad(f"{label}[{index}] has invalid source or media_id.")
    return source, media_id


def _client_event_id(value, label, index):
    if not isinstance(value, str):
        _bad(f"{label}[{index}].client_event_id must be a string.")
    value = value.strip()
    if not value or len(value) > MAX_CLIENT_EVENT_ID_LENGTH:
        _bad(
            f"{label}[{index}].client_event_id must be 1 to {MAX_CLIENT_EVENT_ID_LENGTH} characters."
        )
    return value


def _watched_at(value, label, index):
    parsed = parse_datetime(value) if isinstance(value, str) else None
    # A bare date would silently become midnight; the exact instant is required.
    if parsed is None or not any(mark in value for mark in ("T", " ")):
        _bad(f"{label}[{index}].watched_at must be an ISO-8601 datetime.")
    return make_aware(parsed) if is_naive(parsed) else parsed


def _coordinate(raw, key, label, index, minimum):
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _bad(f"{label}[{index}].{key} must be an integer >= {minimum}.")
    return value


def _episode_uuid(client_event_id):
    """Map a client_event_id to the UUID stored on the episode play."""
    try:
        return UUID(client_event_id)
    except (AttributeError, TypeError, ValueError):
        return uuid5(_OPAQUE_ID_NAMESPACE, client_event_id)


def _with_db_backoff(func):
    """Run ``func``, retrying a locked SQLite write after the shared pauses."""
    for attempt in range(len(DB_LOCK_BACKOFF_SECONDS) + 1):
        try:
            return func()
        except OperationalError as error:
            if "locked" not in str(error).lower() or attempt == len(
                DB_LOCK_BACKOFF_SECONDS
            ):
                raise
            time.sleep(DB_LOCK_BACKOFF_SECONDS[attempt])
    return None  # pragma: no cover


def _failure_reason(error):
    if isinstance(error, OperationalError) and "locked" in str(error).lower():
        return "database_busy"
    return "write_failed"


def _counts(results):
    return dict(Counter(result["outcome"] for result in results))


def _respond(results):
    return Response({"results": results, "counts": _counts(results)}, status=HTTP.OK)


# /api/v1/sync/history/
class SyncHistoryView(drf_views.APIView):
    """Add movie and episode plays at their exact watched instants."""

    @extend_schema(
        request=SyncHistoryRequestSerializer,
        responses={200: SyncHistoryResponseSerializer, **_SYNC_RESPONSES},
    )
    @batched_activity()
    def post(self, request):
        """Store a mixed batch of plays; every input gets one result."""
        data, id_plan = resolve_entry_ids(
            request.data, ("movies", "episodes"), MAX_SYNC_EVENTS
        )
        if id_plan is not None and not has_resolved_entries(data, id_plan):
            return _respond(splice_unresolved([], id_plan, "history"))
        try:
            movies, episodes = self._parse(data)
        except SyncRequestError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)

        results = [None] * (len(movies) + len(episodes))
        with credentials.current_user_scope(request.user):
            self._apply_movies(request.user, movies, results)
            self._apply_episodes(request.user, episodes, results, offset=len(movies))
        if id_plan is not None:
            results = splice_unresolved(results, id_plan, "history")
        return _respond(results)

    def _parse(self, data):
        raw_movies = _list_field(data, "movies")
        raw_episodes = _list_field(data, "episodes")
        total = len(raw_movies) + len(raw_episodes)
        if total == 0:
            _bad("At least one movie or episode event is required.")
        if total > MAX_SYNC_EVENTS:
            _bad(f"At most {MAX_SYNC_EVENTS} events are allowed per request.")

        movies = []
        for index, raw in enumerate(raw_movies):
            raw = _entry(raw, "movies", index)  # noqa: PLW2901
            source, media_id = _media_ref(raw, "movies", index, MediaTypes.MOVIE.value)
            movies.append(
                {
                    "source": source,
                    "media_id": media_id,
                    "title": str(
                        raw.get("title") or f"CineTrack movie {media_id}"
                    ).strip(),
                    "image": "",
                    "status": None,
                    "watched_at": _watched_at(raw.get("watched_at"), "movies", index),
                    "external_id": _client_event_id(
                        raw.get("client_event_id"), "movies", index
                    ),
                }
            )
        episodes = []
        for index, raw in enumerate(raw_episodes):
            raw = _entry(raw, "episodes", index)  # noqa: PLW2901
            source, media_id = _media_ref(raw, "episodes", index, MediaTypes.TV.value)
            client_event_id = _client_event_id(
                raw.get("client_event_id"), "episodes", index
            )
            episodes.append(
                {
                    "source": source,
                    "media_id": media_id,
                    "season_number": _coordinate(
                        raw, "season_number", "episodes", index, 0
                    ),
                    "episode_number": _coordinate(
                        raw, "episode_number", "episodes", index, 1
                    ),
                    "watched_at": _watched_at(raw.get("watched_at"), "episodes", index),
                    "client_event_id": client_event_id,
                    "uuid": _episode_uuid(client_event_id),
                }
            )

        ids = [movie["external_id"] for movie in movies]
        ids += [episode["client_event_id"] for episode in episodes]
        if len(set(ids)) != len(ids):
            _bad("client_event_id values must be unique per request.")
        if len({episode["uuid"] for episode in episodes}) != len(episodes):
            _bad("client_event_id values must be unique per request.")
        if len({(e["source"], e["media_id"]) for e in episodes}) > MAX_SYNC_SHOWS:
            _bad(f"At most {MAX_SYNC_SHOWS} distinct shows are allowed per request.")
        return movies, episodes

    def _apply_movies(self, user, movies, results):
        if not movies:
            return
        try:
            outcomes = _with_db_backoff(
                lambda: ensure_movie_entries(
                    user,
                    movies,
                    detect_conflicts=True,
                    complete_on_advance=True,
                )
            )
        except Exception as error:
            logger.exception("Sync history movie write failed")
            for index, movie in enumerate(movies):
                results[index] = {
                    "client_event_id": movie["external_id"],
                    "type": "movie",
                    "outcome": "failed",
                    "reason": _failure_reason(error),
                }
            return
        for index, (movie, outcome) in enumerate(zip(movies, outcomes, strict=True)):
            result = {
                "client_event_id": movie["external_id"],
                "type": "movie",
                "outcome": outcome.outcome,
            }
            if outcome.outcome == "conflict":
                result["reason"] = "client_event_id_bound_to_other_event"
            results[index] = result

    def _apply_episodes(self, user, episodes, results, *, offset):
        shows = OrderedDict()
        for position, episode in enumerate(episodes):
            shows.setdefault((episode["source"], episode["media_id"]), []).append(
                (position, episode)
            )

        for (source, media_id), group in shows.items():
            events = [
                (e["season_number"], e["episode_number"], e["watched_at"], e["uuid"])
                for _, e in group
            ]
            failure = None
            try:
                ensured = ensure_episode_events(
                    user,
                    source,
                    media_id,
                    events,
                    conflicts="item",
                )
                outcomes, stored, reasons, titles = ensured
            except EpisodeEnsureError as error:
                reason = {
                    "metadata": "provider_unavailable",
                    "busy": "database_busy",
                }.get(error.kind, "write_failed")
                failure = (error.kind, reason)
                partial = error.partial
            except Exception as error:
                logger.exception(
                    "Sync history episode write failed media_id=%s", media_id
                )
                failure = ("error", _failure_reason(error))
                partial = None
            if failure is not None:
                outcomes, stored, reasons, titles = partial or ({}, {}, {}, {})
            for position, episode in group:
                results[offset + position] = self._episode_result(
                    episode,
                    outcomes.get(episode["uuid"]),
                    stored=stored,
                    reasons=reasons,
                    titles=titles,
                    failure=failure,
                )

    @staticmethod
    def _episode_result(episode, outcome, *, stored, reasons, titles, failure):
        event_id = episode["uuid"]
        result = {
            "client_event_id": episode["client_event_id"],
            "type": "episode",
        }
        if outcome is None:
            kind, reason = failure or ("error", "unresolved")
            result["outcome"] = (
                "metadata_unavailable" if kind == "metadata" else "failed"
            )
            result["reason"] = reason
            return result
        result["outcome"] = outcome
        if event_id in stored and outcome in _WRITTEN:
            result["stored_season_number"], result["stored_episode_number"] = stored[
                event_id
            ]
        if outcome in {"not_found", "metadata_unavailable"}:
            result["reason"] = reasons.get(event_id, "no_tmdb_episode")
            if event_id in titles:
                result["title"] = titles[event_id]
        elif outcome == "conflict":
            result["reason"] = "client_event_id_bound_to_other_event"
        return result


def _parse_selector(raw, label, index):
    """Return ("client_event_id"|"watched_at"|"all", value); exactly one is required."""
    present = [key for key in ("client_event_id", "watched_at", "all") if key in raw]
    if len(present) != 1:
        _bad(
            f"{label}[{index}] needs exactly one of client_event_id, watched_at, or all."
        )
    key = present[0]
    if key == "client_event_id":
        return key, _client_event_id(raw["client_event_id"], label, index)
    if key == "watched_at":
        return key, _watched_at(raw["watched_at"], label, index)
    if raw["all"] is not True:
        _bad(f"{label}[{index}].all must be true.")
    return key, True


# /api/v1/sync/history/remove/
class SyncHistoryRemoveView(drf_views.APIView):
    """Remove plays by an explicit selector; never by coordinates alone."""

    @extend_schema(
        request=SyncRemoveRequestSerializer,
        responses={200: SyncItemsResponseSerializer, **_SYNC_RESPONSES},
    )
    @batched_activity()
    def post(self, request):
        """Remove the plays each item selects; every input gets one result."""
        data, id_plan = resolve_entry_ids(
            request.data, ("movies", "episodes"), MAX_SYNC_REMOVALS
        )
        if id_plan is not None and not has_resolved_entries(data, id_plan):
            return _respond(splice_unresolved([], id_plan, "items"))
        try:
            movies, episodes = self._parse(data)
        except SyncRequestError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)

        touched_seasons = {}
        results = [
            self._guarded(self._remove_movie, request.user, item) for item in movies
        ]
        results += [
            self._guarded(self._remove_episode, request.user, item, touched_seasons)
            for item in episodes
        ]
        for season in touched_seasons.values():
            self._refresh_season(season)
        if id_plan is not None:
            results = splice_unresolved(results, id_plan, "items")
        return _respond(results)

    def _parse(self, data):
        raw_movies = _list_field(data, "movies")
        raw_episodes = _list_field(data, "episodes")
        total = len(raw_movies) + len(raw_episodes)
        if total == 0:
            _bad("At least one movie or episode removal is required.")
        if total > MAX_SYNC_REMOVALS:
            _bad(f"At most {MAX_SYNC_REMOVALS} removals are allowed per request.")
        movies = []
        for index, raw in enumerate(raw_movies):
            raw = _entry(raw, "movies", index)  # noqa: PLW2901
            source, media_id = _media_ref(raw, "movies", index, MediaTypes.MOVIE.value)
            selector, value = _parse_selector(raw, "movies", index)
            movies.append(
                {
                    "type": "movie",
                    "source": source,
                    "media_id": media_id,
                    "selector": selector,
                    "value": value,
                }
            )
        episodes = []
        for index, raw in enumerate(raw_episodes):
            raw = _entry(raw, "episodes", index)  # noqa: PLW2901
            source, media_id = _media_ref(raw, "episodes", index, MediaTypes.TV.value)
            selector, value = _parse_selector(raw, "episodes", index)
            episodes.append(
                {
                    "type": "episode",
                    "source": source,
                    "media_id": media_id,
                    "season_number": _coordinate(
                        raw, "season_number", "episodes", index, 0
                    ),
                    "episode_number": _coordinate(
                        raw, "episode_number", "episodes", index, 1
                    ),
                    "selector": selector,
                    "value": value,
                }
            )
        return movies, episodes

    @staticmethod
    def _base(item):
        result = {
            "type": item["type"],
            "source": item["source"],
            "media_id": item["media_id"],
        }
        if item["type"] == "episode":
            result["season_number"] = item["season_number"]
            result["episode_number"] = item["episode_number"]
        if item["selector"] == "client_event_id":
            result["client_event_id"] = item["value"]
        return result

    def _guarded(self, func, user, item, *extra):
        result = self._base(item)
        try:
            outcome, removed = _with_db_backoff(lambda: func(user, item, *extra))
        except Exception as error:
            logger.exception(
                "Sync history removal failed type=%s media_id=%s",
                item["type"],
                item["media_id"],
            )
            result.update(outcome="failed", reason=_failure_reason(error))
            return result
        result["outcome"] = outcome
        if outcome == "removed":
            result["removed_count"] = removed
        elif outcome == "conflict":
            result["reason"] = "client_event_id_bound_to_other_event"
        return result

    @staticmethod
    def _remove_movie(user, item):
        selector, value = item["selector"], item["value"]
        movie_plays = MoviePlay.objects.filter(movie__user=user)
        with transaction.atomic():
            if selector == "client_event_id":
                play = (
                    movie_plays.filter(external_id=value)
                    .select_related("movie__item")
                    .first()
                )
                if play is None:
                    return "already_satisfied", 0
                movie_item = play.movie.item
                if (str(movie_item.media_id), movie_item.source) != (
                    item["media_id"],
                    item["source"],
                ):
                    return "conflict", 0
                movie = play.movie
                plays = [play]
            else:
                # A repeat can be its own Movie row, so every row of this title
                # is in scope, not only the first.
                movies = list(
                    Movie.objects.filter(
                        user=user,
                        item__media_id=item["media_id"],
                        item__source=item["source"],
                        item__media_type=MediaTypes.MOVIE.value,
                    ).order_by("id"),
                )
                if not movies:
                    return "already_satisfied", 0
                removed = 0
                for movie in movies:
                    plays = movie.plays.all()
                    if selector == "watched_at":
                        plays = plays.filter(end_date=value)
                    plays = list(plays)
                    for play in plays:
                        play.delete()
                    removed += len(plays)
                    remaining = movie.plays.order_by("-end_date", "-id").first()
                    if remaining is not None:
                        new_end_date = remaining.end_date
                    elif movie.end_date is not None and (
                        selector == "all" or movie.end_date == value
                    ):
                        # A legacy watch is only Movie.end_date, with no play row.
                        # Answering already_satisfied here would let a client
                        # acknowledge a removal while the title stays watched.
                        new_end_date = None
                        if not plays:
                            removed += 1
                    else:
                        new_end_date = movie.end_date if not plays else None
                    if new_end_date != movie.end_date:
                        # Same bookkeeping as Movie.unwatch: end_date follows the
                        # latest remaining play.
                        movie.end_date = new_end_date
                        movie.save(update_fields=["end_date"])
                if not removed:
                    return "already_satisfied", 0
                return "removed", removed
            for play in plays:
                play.delete()
            # Same bookkeeping as Movie.unwatch: end_date follows the latest play.
            latest = movie.plays.order_by("-end_date", "-id").first()
            movie.end_date = latest.end_date if latest else None
            movie.save(update_fields=["end_date"])
            return "removed", len(plays)

    @staticmethod
    def _remove_episode(user, item, touched_seasons):
        selector, value = item["selector"], item["value"]
        with transaction.atomic():
            if selector == "client_event_id":
                play = (
                    Episode.objects.filter(
                        watch_operation_id=_episode_uuid(value),
                        related_season__user=user,
                    )
                    .select_related("related_season__item")
                    .first()
                )
                if play is None:
                    return "already_satisfied", 0
                season_item = play.related_season.item
                if (str(season_item.media_id), season_item.source) != (
                    item["media_id"],
                    item["source"],
                ):
                    return "conflict", 0
                plays = [play]
                season = play.related_season
            else:
                season = metadata_resolution.find_tracked_season(
                    user,
                    item["media_id"],
                    item["source"],
                    item["season_number"],
                )
                if season is None:
                    return "already_satisfied", 0
                plays = Episode.objects.filter(
                    related_season=season,
                    item__episode_number=item["episode_number"],
                )
                if selector == "watched_at":
                    plays = plays.filter(end_date=value)
                plays = list(plays)
            if not plays:
                return "already_satisfied", 0
            for play in plays:
                play.delete()
            touched_seasons[season.id] = season
            return "removed", len(plays)

    @staticmethod
    def _refresh_season(season):
        """Re-evaluate season/TV status and caches once, as Season.unwatch does."""
        if hasattr(season, "_episode_stats_cache"):
            delattr(season, "_episode_stats_cache")
        season._sync_status_after_episode_change()
        cache_utils.clear_time_left_cache_for_user(season.user_id)
        cache_utils.clear_media_list_cache_for_user(season.user_id)


def _parse_score(raw, label, index):
    if "score" not in raw:
        _bad(f"{label}[{index}].score is required (0-10 or null).")
    value = raw["score"]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        _bad(f"{label}[{index}].score must be a number or null.")
    try:
        score = Decimal(str(value))
    except (InvalidOperation, ValueError):
        _bad(f"{label}[{index}].score must be a number or null.")
    if not score.is_finite() or not Decimal(0) <= score <= Decimal(10):
        _bad(f"{label}[{index}].score must be between 0 and 10.")
    return score.quantize(_SCORE_STEP, rounding=ROUND_HALF_UP)


# /api/v1/sync/ratings/
class SyncRatingsView(drf_views.APIView):
    """Set or clear scores on already-tracked items; never creates tracking rows."""

    @extend_schema(
        request=SyncRatingsRequestSerializer,
        responses={200: SyncItemsResponseSerializer, **_SYNC_RESPONSES},
    )
    @batched_activity()
    def post(self, request):
        """Apply each score; every input gets one result."""
        data, id_plan = resolve_entry_ids(
            request.data, ("movies", "shows", "episodes"), MAX_SYNC_RATINGS
        )
        if id_plan is not None and not has_resolved_entries(data, id_plan):
            return _respond(splice_unresolved([], id_plan, "items"))
        try:
            items = self._parse(data)
        except SyncRequestError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)

        results = []
        for item in items:
            result = {
                "type": item["type"],
                "source": item["source"],
                "media_id": item["media_id"],
            }
            if item["type"] == "episode":
                result["season_number"] = item["season_number"]
                result["episode_number"] = item["episode_number"]
            try:
                result["outcome"] = _with_db_backoff(
                    lambda item=item: self._apply(request.user, item)
                )
            except Exception as error:
                logger.exception(
                    "Sync rating failed type=%s media_id=%s",
                    item["type"],
                    item["media_id"],
                )
                result.update(outcome="failed", reason=_failure_reason(error))
            results.append(result)
        if id_plan is not None:
            results = splice_unresolved(results, id_plan, "items")
        return _respond(results)

    def _parse(self, data):
        raw_movies = _list_field(data, "movies")
        raw_shows = _list_field(data, "shows")
        raw_episodes = _list_field(data, "episodes")
        total = len(raw_movies) + len(raw_shows) + len(raw_episodes)
        if total == 0:
            _bad("At least one rating is required.")
        if total > MAX_SYNC_RATINGS:
            _bad(f"At most {MAX_SYNC_RATINGS} ratings are allowed per request.")
        items = []
        for label, raw_items, item_type, media_type in (
            ("movies", raw_movies, "movie", MediaTypes.MOVIE.value),
            ("shows", raw_shows, "show", MediaTypes.TV.value),
            ("episodes", raw_episodes, "episode", MediaTypes.TV.value),
        ):
            for index, raw in enumerate(raw_items):
                raw = _entry(raw, label, index)  # noqa: PLW2901
                source, media_id = _media_ref(raw, label, index, media_type)
                item = {
                    "type": item_type,
                    "source": source,
                    "media_id": media_id,
                    "score": _parse_score(raw, label, index),
                }
                if item_type == "episode":
                    item["season_number"] = _coordinate(
                        raw, "season_number", label, index, 0
                    )
                    item["episode_number"] = _coordinate(
                        raw, "episode_number", label, index, 1
                    )
                items.append(item)
        return items

    @staticmethod
    def _apply(user, item):
        score = item["score"]
        with transaction.atomic():
            if item["type"] == "episode":
                season = metadata_resolution.find_tracked_season(
                    user,
                    item["media_id"],
                    item["source"],
                    item["season_number"],
                )
                if season is None:
                    return "not_found"
                scores = list(
                    Episode.objects.filter(
                        related_season=season,
                        item__episode_number=item["episode_number"],
                    ).values_list("score", flat=True),
                )
                if not scores:
                    return "not_found"
                if all(existing == score for existing in scores):
                    return "already_satisfied"
                apply_episode_score(season, item["episode_number"], score)
                return "updated"

            media_type = (
                MediaTypes.MOVIE.value
                if item["type"] == "movie"
                else MediaTypes.TV.value
            )
            media = BasicMedia.objects.filter_media(
                user,
                item["media_id"],
                media_type,
                item["source"],
            ).first()
            if media is None:
                return "not_found"
            if media.score == score:
                return "already_satisfied"
            media.score = score
            media.save()
            return "updated"


# /api/v1/sync/status/
class SyncStatusView(drf_views.APIView):
    """Set library status on movies and shows without creating episode history."""

    @extend_schema(
        request=SyncStatusRequestSerializer,
        responses={200: SyncItemsResponseSerializer, **_SYNC_RESPONSES},
    )
    @batched_activity()
    def post(self, request):
        """Create or update each item's status; every input gets one result."""
        data, id_plan = resolve_entry_ids(
            request.data, ("movies", "shows"), MAX_SYNC_STATUS_ITEMS
        )
        if id_plan is not None and not has_resolved_entries(data, id_plan):
            return _respond(splice_unresolved([], id_plan, "items"))
        try:
            items = self._parse(data)
        except SyncRequestError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)

        results = [
            {
                "type": item["type"],
                "source": item["source"],
                "media_id": item["media_id"],
            }
            for item in items
        ]
        with credentials.current_user_scope(request.user):
            for item_type, ensure in (
                ("movie", self._ensure_movies),
                ("show", self._ensure_shows),
            ):
                subset = [
                    (i, item)
                    for i, item in enumerate(items)
                    if item["type"] == item_type
                ]
                if subset:
                    self._apply(request.user, subset, results, ensure)
        if id_plan is not None:
            results = splice_unresolved(results, id_plan, "items")
        return _respond(results)

    def _parse(self, data):
        raw_movies = _list_field(data, "movies")
        raw_shows = _list_field(data, "shows")
        total = len(raw_movies) + len(raw_shows)
        if total == 0:
            _bad("At least one movie or show status is required.")
        if total > MAX_SYNC_STATUS_ITEMS:
            _bad(f"At most {MAX_SYNC_STATUS_ITEMS} statuses are allowed per request.")
        items = []
        seen = set()
        for label, raw_items, item_type, media_type in (
            ("movies", raw_movies, "movie", MediaTypes.MOVIE.value),
            ("shows", raw_shows, "show", MediaTypes.TV.value),
        ):
            for index, raw in enumerate(raw_items):
                raw = _entry(raw, label, index)  # noqa: PLW2901
                source, media_id = _media_ref(raw, label, index, media_type)
                status = _STATUS_BY_NAME.get(
                    str(raw.get("status") or "").strip().lower()
                )
                if status is None:
                    _bad(
                        f"{label}[{index}].status must be one of {', '.join(_STATUS_BY_NAME)}."
                    )
                if (item_type, source, media_id) in seen:
                    _bad(f"{label}[{index}] repeats an item already in this request.")
                seen.add((item_type, source, media_id))
                default_title = f"CineTrack {'movie' if item_type == 'movie' else 'show'} {media_id}"
                items.append(
                    {
                        "type": item_type,
                        "source": source,
                        "media_id": media_id,
                        "status": status,
                        "title": str(raw.get("title") or default_title).strip(),
                        "title_given": bool(raw.get("title")),
                        "image": "",
                    }
                )
        return items

    @staticmethod
    def _ensure_movies(user, entries):
        return ensure_movie_entries(
            user,
            [{**entry, "watched_at": None, "external_id": None} for entry in entries],
        )

    @staticmethod
    def _ensure_shows(user, entries):
        return ensure_show_entries(user, entries)

    def _apply(self, user, subset, results, ensure):
        known = self._known_items(subset)
        placeable = []
        for position, item in subset:
            if (item["source"], item["media_id"]) not in known:
                found = self._provider_lookup(item)
                if found is None:
                    results[position].update(
                        outcome="not_found", reason="unknown_to_provider"
                    )
                    continue
                if found is False:
                    results[position].update(
                        outcome="failed", reason="provider_unavailable"
                    )
                    continue
                if not item["title_given"]:
                    item["title"] = found.get("title") or item["title"]
                item["image"] = found.get("image") or ""
            placeable.append((position, item))
        if not placeable:
            return
        try:
            outcomes = _with_db_backoff(
                lambda: ensure(user, [item for _, item in placeable])
            )
        except Exception as error:
            logger.exception("Sync status write failed")
            for position, _ in placeable:
                results[position].update(
                    outcome="failed", reason=_failure_reason(error)
                )
            return
        for (position, _), outcome in zip(placeable, outcomes, strict=True):
            if outcome.created:
                label = "created"
            elif outcome.changed:
                label = "updated"
            else:
                label = "already_satisfied"
            results[position]["outcome"] = label

    @staticmethod
    def _known_items(subset):
        media_type = (
            MediaTypes.MOVIE.value
            if subset[0][1]["type"] == "movie"
            else MediaTypes.TV.value
        )
        queryset = Item.objects.filter(
            media_type=media_type,
            source__in={item["source"] for _, item in subset},
            media_id__in={item["media_id"] for _, item in subset},
        )
        if media_type == MediaTypes.TV.value:
            queryset = queryset.filter(season_number__isnull=True).exclude(
                library_media_type=MediaTypes.ANIME.value,
            )
        return {(row.source, str(row.media_id)) for row in queryset}

    @staticmethod
    def _provider_lookup(item):
        """Return metadata when the provider knows the item, None when it does not.

        ``False`` means the provider could not be asked (not a verdict).
        """
        media_type = (
            MediaTypes.MOVIE.value if item["type"] == "movie" else MediaTypes.TV.value
        )
        try:
            metadata = services.get_media_metadata(
                media_type, item["media_id"], item["source"]
            )
        except services.ProviderAPIError as error:
            if error.status_code == HTTP.NOT_FOUND:
                return None
            logger.warning(
                "Sync status provider lookup failed media_id=%s status=%s",
                item["media_id"],
                error.status_code,
            )
            return False
        except Exception:
            logger.warning(
                "Sync status provider lookup failed media_id=%s",
                item["media_id"],
                exc_info=True,
            )
            return False
        if not isinstance(metadata, dict) or not metadata:
            return None
        return metadata
