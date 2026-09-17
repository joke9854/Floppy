"""High-throughput CineTrack bootstrap endpoints for the Floppy fork.

These endpoints assert durable tracking facts first and deliberately keep
provider metadata hydration off the request path.  They are isolated from the
upstream-compatible tracking views so the fork remains easy to rebase.
"""

import logging
from collections import defaultdict
from http import HTTPStatus as HTTP  # noqa: N814
from uuid import UUID

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, views as drf_views
from rest_framework.response import Response

from app import cache_utils
from app.fork_services_episode import create_episode_watch
from app.models import Episode, Item, MediaTypes, Movie, MoviePlay, Season, Status, TV
from app.providers import services
from app.services import metadata_resolution
from app.services.episode_coordinates import (
    EpisodeMetadataUnavailableError,
    InvalidEpisodeCoordinateError,
    cleanup_episode_history_for_route,
    resolve_episode_coordinate,
)
from app.tasks_metadata_cache import queue_cinetrack_bootstrap_hydration

from .helpers import check_source_type, try_parse_datetime_input
from .schema import MEDIA_TYPE_TV_ONLY_PARAM

logger = logging.getLogger(__name__)
MAX_BOOTSTRAP_ITEMS = 50
MAX_EPISODE_EVENTS = 50
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
    movies = CineTrackMovieInputSerializer(many=True)


class CineTrackShowInputSerializer(serializers.Serializer):
    source = serializers.CharField()
    media_id = serializers.CharField()
    title = serializers.CharField(required=False, allow_blank=True)
    image = serializers.CharField(required=False, allow_blank=True)
    status = serializers.JSONField(required=False)


class CineTrackShowsEnsureRequestSerializer(serializers.Serializer):
    shows = CineTrackShowInputSerializer(many=True)


class CineTrackEpisodeEventInputSerializer(serializers.Serializer):
    season_number = serializers.IntegerField(min_value=1)
    episode_number = serializers.IntegerField(min_value=1)
    watched_at = serializers.DateTimeField()
    client_event_id = serializers.UUIDField()


class CineTrackEpisodeEnsureRequestSerializer(serializers.Serializer):
    events = CineTrackEpisodeEventInputSerializer(many=True)
    library_media_type = serializers.CharField(required=False, allow_blank=True)


class CineTrackBootstrapResultSerializer(serializers.Serializer):
    source = serializers.CharField(required=False)
    media_id = serializers.CharField(required=False)
    client_event_id = serializers.CharField(required=False)
    season_number = serializers.IntegerField(required=False)
    episode_number = serializers.IntegerField(required=False)
    status = serializers.ChoiceField(choices=("created", "already_satisfied"))


class CineTrackBootstrapResponseSerializer(serializers.Serializer):
    results = CineTrackBootstrapResultSerializer(many=True)


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


class CineTrackBootstrapMoviesEnsureView(drf_views.APIView):
    """Ensure a bounded batch of movie state without provider I/O per item."""

    @extend_schema(
        request=CineTrackMoviesEnsureRequestSerializer,
        responses={200: CineTrackBootstrapResponseSerializer},
    )
    def post(self, request):
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
        with transaction.atomic():
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
            movies = {
                movie.item_id: movie
                for movie in Movie.objects.filter(user=request.user, item_id__in=item_ids)
            }
            created_movie_ids = set()
            for item_id in item_ids:
                if item_id in movies:
                    continue
                movie = Movie(
                    user=request.user,
                    item_id=item_id,
                    status=Status.IN_PROGRESS.value,
                    score=None,
                    notes="",
                    created_at=timezone.now(),
                )
                movie.save_base(raw=True, force_insert=True)
                movies[item_id] = movie
                created_movie_ids.add(movie.id)

            external_ids = {e["external_id"] for e in parsed if e["external_id"]}
            existing_plays = {
                (play.movie_id, play.external_id): play
                for play in MoviePlay.objects.filter(
                    movie_id__in=[movie.id for movie in movies.values()],
                    external_id__in=external_ids,
                )
            }
            watch_dates = {e["watched_at"] for e in parsed if e["watched_at"] is not None}
            legacy_plays = defaultdict(list)
            if watch_dates:
                for play in MoviePlay.objects.filter(
                    movie_id__in=[movie.id for movie in movies.values()],
                    end_date__in=watch_dates,
                ).filter(Q(external_id__isnull=True) | Q(external_id="")).order_by("id"):
                    legacy_plays[(play.movie_id, play.end_date)].append(play)

            dirty_movies = {}
            for entry in parsed:
                item = items[_item_key(entry["source"], entry["media_id"])]
                movie = movies[item.id]
                changed = movie.id in created_movie_ids
                if movie.status != entry["status"]:
                    movie.status = entry["status"]
                    changed = True

                outcome = "created" if movie.id in created_movie_ids else "already_satisfied"
                watched_at = entry["watched_at"]
                external_id = entry["external_id"]
                if watched_at is not None:
                    play = existing_plays.get((movie.id, external_id))
                    if play is None:
                        legacy_candidates = legacy_plays.get((movie.id, watched_at), [])
                        if legacy_candidates:
                            play = legacy_candidates.pop(0)
                            play.external_id = external_id
                            play.save(update_fields=["external_id"])
                            existing_plays[(movie.id, external_id)] = play
                            outcome = "already_satisfied"
                        elif movie.end_date == watched_at and not movie.plays.exists():
                            play, _ = MoviePlay.objects.get_or_create(
                                movie=movie,
                                external_id=external_id,
                                defaults={"end_date": watched_at},
                            )
                            existing_plays[(movie.id, external_id)] = play
                            outcome = "already_satisfied"
                        else:
                            play, created = MoviePlay.objects.get_or_create(
                                movie=movie,
                                external_id=external_id,
                                defaults={"end_date": watched_at},
                            )
                            existing_plays[(movie.id, external_id)] = play
                            outcome = "created" if created else "already_satisfied"
                    if movie.end_date is None or watched_at > movie.end_date:
                        movie.end_date = watched_at
                        changed = True
                if changed:
                    dirty_movies[movie.id] = movie
                results.append({
                    "source": entry["source"],
                    "media_id": entry["media_id"],
                    "status": outcome,
                })

            if dirty_movies:
                Movie.objects.bulk_update(
                    list(dirty_movies.values()),
                    fields=["status", "end_date"],
                )
            queue_cinetrack_bootstrap_hydration(hydration_ids, request.user.id)

        return Response({"results": results}, status=HTTP.OK)


class CineTrackBootstrapShowsEnsureView(drf_views.APIView):
    """Ensure show library state without manufacturing episode history."""

    @extend_schema(
        request=CineTrackShowsEnsureRequestSerializer,
        responses={200: CineTrackBootstrapResponseSerializer},
    )
    def post(self, request):
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
            tv_rows = {
                tv.item_id: tv
                for tv in TV.objects.filter(user=request.user, item_id__in=item_ids)
            }
            dirty = []
            created_ids = set()
            for item_id in item_ids:
                if item_id in tv_rows:
                    continue
                tv = TV(
                    user=request.user,
                    item_id=item_id,
                    status=Status.IN_PROGRESS.value,
                    score=None,
                    notes="",
                    created_at=timezone.now(),
                )
                tv.save_base(raw=True, force_insert=True)
                tv_rows[item_id] = tv
                created_ids.add(tv.id)

            for entry in parsed:
                item = items[_item_key(entry["source"], entry["media_id"])]
                tv = tv_rows[item.id]
                changed = tv.id in created_ids
                if tv.status != entry["status"]:
                    tv.status = entry["status"]
                    changed = True
                if changed:
                    dirty.append(tv)
                results.append({
                    "source": entry["source"],
                    "media_id": entry["media_id"],
                    "status": "created" if changed else "already_satisfied",
                })

            if dirty:
                TV.objects.bulk_update(dirty, fields=["status"])
            queue_cinetrack_bootstrap_hydration(hydration_ids, request.user.id)

        return Response({"results": results}, status=HTTP.OK)


class MediaEpisodeEnsureView(drf_views.APIView):
    """Ensure exact episode-watch events with one metadata fetch per batch."""

    @extend_schema(
        parameters=[MEDIA_TYPE_TV_ONLY_PARAM],
        request=CineTrackEpisodeEnsureRequestSerializer,
        responses={200: CineTrackBootstrapResponseSerializer},
    )
    def post(self, request, media_type, source, media_id):
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
            if season_number < 1 or episode_number < 1 or watched_at is None:
                return Response({"detail": f"events[{index}] has invalid coordinates or watched_at."}, status=HTTP.BAD_REQUEST)
            parsed.append((season_number, episode_number, watched_at, client_event_id))

        if len({event[3] for event in parsed}) != len(parsed):
            return Response({"detail": "client_event_id values must be unique per request."}, status=HTTP.BAD_REQUEST)

        client_ids = [event[3] for event in parsed]
        claimed_by_id = {
            episode.watch_operation_id: episode
            for episode in Episode.objects.filter(
                watch_operation_id__in=client_ids,
            ).select_related("related_season__item", "item")
        }
        outcomes = {}
        unresolved = []
        for season_number, episode_number, watched_at, client_event_id in parsed:
            claimed = claimed_by_id.get(client_event_id)
            if claimed is None:
                unresolved.append((season_number, episode_number, watched_at, client_event_id))
                continue
            same_identity = (
                claimed.related_season.user_id == request.user.id
                and str(claimed.related_season.item.media_id) == str(media_id)
                and claimed.related_season.item.source == source
                and claimed.related_season.item.season_number == season_number
                and claimed.item.episode_number == episode_number
                and claimed.end_date == watched_at
            )
            if not same_identity:
                return Response({"detail": "client_event_id belongs to another episode event."}, status=HTTP.CONFLICT)
            outcomes[client_event_id] = "already_satisfied"

        if unresolved:
            season_numbers = sorted({event[0] for event in unresolved})
            try:
                combined_metadata = services.get_media_metadata(
                    "tv_with_seasons",
                    media_id,
                    source,
                    season_numbers,
                )
            except Exception:
                logger.exception("CineTrack episode metadata batch failed media_id=%s", media_id)
                return Response({"detail": "Could not resolve episode events."}, status=HTTP.NOT_FOUND)

            metadata_by_season = {}
            for season_number in season_numbers:
                season_metadata = combined_metadata.get(f"season/{season_number}")
                if not isinstance(season_metadata, dict) and len(season_numbers) == 1 and isinstance(combined_metadata.get("episodes"), list):
                    season_metadata = combined_metadata
                if not isinstance(season_metadata, dict):
                    return Response({"detail": f"Season {season_number} metadata is unavailable."}, status=HTTP.NOT_FOUND)
                # Avoid a secondary TVDB artwork lookup in the bootstrap request;
                # the authoritative episode list is already present and rich
                # metadata can be hydrated asynchronously later.
                season_metadata.setdefault("_tvdb_episode_image_map", {})
                metadata_by_season[season_number] = season_metadata

            library_media_type = str(request.data.get("library_media_type") or "").strip()
            for season_number, episode_number, _, _ in unresolved:
                try:
                    resolve_episode_coordinate(
                        media_id,
                        source,
                        season_number,
                        episode_number,
                        season_metadata=metadata_by_season[season_number],
                    )
                except InvalidEpisodeCoordinateError:
                    cleanup_episode_history_for_route(
                        request.user,
                        media_id,
                        source,
                        season_number,
                        episode_number,
                        library_media_type=library_media_type or None,
                    )
                    return Response({"detail": "Episode not found."}, status=HTTP.NOT_FOUND)
                except EpisodeMetadataUnavailableError:
                    return Response({"detail": "Episode metadata is unavailable."}, status=HTTP.NOT_FOUND)

            created_any = False
            try:
                with transaction.atomic():
                    seasons = {}
                    for season_number in season_numbers:
                        seasons[season_number] = _ensure_season_from_metadata(
                            request.user,
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

                    for season_number, episode_number, watched_at, client_event_id in unresolved:
                        season = seasons[season_number]
                        legacy_key = (season.id, episode_number, watched_at)
                        legacy_candidates = legacy_by_key.get(legacy_key, [])
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
                                        return Response(
                                            {"detail": "client_event_id conflicts with an existing episode event."},
                                            status=HTTP.CONFLICT,
                                        )
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
            except Exception:
                logger.exception("CineTrack episode ensure failed media_id=%s", media_id)
                return Response({"detail": "Could not ensure episode events."}, status=HTTP.INTERNAL_SERVER_ERROR)

            if created_any:
                cache_utils.clear_time_left_cache_for_user(request.user.id)
                cache_utils.clear_media_list_cache_for_user(request.user.id)

        results = [
            {
                "client_event_id": str(client_event_id),
                "season_number": season_number,
                "episode_number": episode_number,
                "status": outcomes[client_event_id],
            }
            for season_number, episode_number, _watched_at, client_event_id in parsed
        ]
        return Response({"results": results}, status=HTTP.OK)


# Scoped-token enforcement keys views by module.ClassName.  Preserve the
# existing public keys so the optimized implementation is a transparent server
# upgrade rather than a new permission surface.
CineTrackBootstrapMoviesEnsureView.__module__ = "api.fork_views_tracking"
CineTrackBootstrapShowsEnsureView.__module__ = "api.fork_views_tracking"
MediaEpisodeEnsureView.__module__ = "api.fork_views_tracking"
