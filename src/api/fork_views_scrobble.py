# FORK: generic scrobble endpoint for third-party playback clients (e.g.
# streaming apps that aren't Plex/Jellyfin/Emby). Kept separate from
# fork_views_tracking.py since it's a public integration surface rather
# than a web-UI parity mirror. URL wiring lives in fork_urls.py.
import logging
from http import HTTPStatus as HTTP  # noqa: N814

from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import views as drf_views
from rest_framework.response import Response

import app.providers.tmdb
from app import live_playback
from app.models import MediaTypes, Sources
from integrations.delivery import get_or_record_receipt
from integrations.models import IntegrationToken
from integrations.webhooks.base import PLAY_DUPLICATE
from integrations.webhooks.generic_scrobble import GenericScrobbleProcessor, is_played

from . import fork_views_playback
from .helpers import (
    apply_episode_score,
    get_tracked_season,
    try_parse_datetime_input,
    validate_episode_score,
)

logger = logging.getLogger(__name__)

_ACTIONS = ("start", "pause", "stop")
_MEDIA_TYPES = (MediaTypes.MOVIE.value, MediaTypes.EPISODE.value)
_EVENT_TYPE_MAP = {
    "start": "media.play",
    "pause": "media.pause",
    "stop": "media.stop",
}


def _scrobble_request_error(data):
    """Return a 400 Response if the scrobble payload is malformed, else None."""
    action = data.get("action")
    if action not in _ACTIONS:
        return Response(
            {"detail": f"'action' must be one of {_ACTIONS}."},
            status=HTTP.BAD_REQUEST,
        )

    media_type = data.get("media_type")
    if media_type not in _MEDIA_TYPES:
        return Response(
            {"detail": f"'media_type' must be one of {_MEDIA_TYPES}."},
            status=HTTP.BAD_REQUEST,
        )

    ids = data.get("ids") or {}
    if not any(ids.get(key) for key in ("tmdb", "imdb", "tvdb")):
        return Response(
            {"detail": "'ids' must include at least one of tmdb/imdb/tvdb."},
            status=HTTP.BAD_REQUEST,
        )

    if media_type == MediaTypes.EPISODE.value and (
        data.get("season_number") is None or data.get("episode_number") is None
    ):
        return Response(
            {
                "detail": (
                    "'season_number' and 'episode_number' are required "
                    "for media_type 'episode'."
                ),
            },
            status=HTTP.BAD_REQUEST,
        )

    raw_played_at = data.get("played_at")
    if raw_played_at:
        try:
            try_parse_datetime_input(raw_played_at)
        except (TypeError, ValueError):
            return Response(
                {"detail": "Invalid played_at format."},
                status=HTTP.BAD_REQUEST,
            )

    if data.get("progress") is not None:
        progress = data.get("progress")
        if (
            isinstance(progress, bool)
            or not isinstance(progress, (int, float))
            or not 0 <= progress <= 100  # noqa: PLR2004
        ):
            return Response(
                {"detail": "'progress' must be a number from 0 to 100."},
                status=HTTP.BAD_REQUEST,
            )

    if "score" in data:
        _, score_error = validate_episode_score(data.get("score"))
        if score_error:
            return score_error

    return None


def _progress_percent(data):
    """Return how far playback got, 0-100, or None when it cannot be told.

    An explicit ``progress`` wins; otherwise it is derived from the position
    and duration.
    """
    if data.get("progress") is not None:
        return float(data["progress"])
    position = data.get("position_seconds")
    duration = data.get("duration_seconds")
    if position is None or not duration:
        return None
    return min(100.0, max(0.0, position * 100 / duration))


def _position_seconds(data, percent):
    """Return the resume position, derived from ``progress`` when not sent."""
    position = data.get("position_seconds")
    if position is not None:
        return position
    duration = data.get("duration_seconds")
    if percent is None or not duration:
        return None
    return int(duration * percent / 100)


def _is_watched(user, data, percent):
    """Decide whether a stop counts as watched.

    ``completed`` from the client wins. Otherwise the progress is compared
    with the user's threshold (``scrobble_watched_percent``, 80% by default).
    Without a duration, the shared fallback rule (a long enough position)
    applies.
    """
    if data.get("completed") is not None:
        return bool(data["completed"])
    if percent is not None:
        return percent >= user.scrobble_watched_percent
    return is_played(data)


def _scrobble_response(action, percent, *, watched=False, duplicate=None):
    """Describe what the server did with the event."""
    return Response(
        {
            "detail": "accepted",
            # Trakt-style: a stop that counts as watched is a "scrobble"; one
            # that does not is kept as a "pause" (resume position only).
            "action": action,
            "progress": round(percent, 2) if percent is not None else None,
            "watched": watched,
            "duplicate": duplicate,
        },
        status=HTTP.OK,
    )


def _resolve_live_playback_media_id(media_type, ids):
    """Best-effort tmdb id resolution for the Now Playing card.

    Falls back to a single TMDB find() lookup when only imdb/tvdb ids are
    given. Failures are swallowed — the live card is best-effort and must
    never block a client's playback loop.
    """
    if ids.get("tmdb"):
        return str(ids["tmdb"])

    ext_id = ids.get("imdb") or ids.get("tvdb")
    ext_type = "imdb_id" if ids.get("imdb") else "tvdb_id"
    if not ext_id:
        return None

    try:
        find_response = app.providers.tmdb.find(ext_id, ext_type)
    except Exception:
        logger.warning("Scrobble live-playback id resolution failed", exc_info=True)
        return None

    if media_type == MediaTypes.MOVIE.value:
        results = find_response.get("movie_results") or []
        return str(results[0]["id"]) if results else None

    episode_results = find_response.get("tv_episode_results") or []
    if episode_results:
        return str(episode_results[0]["show_id"])
    tv_results = find_response.get("tv_results") or []
    return str(tv_results[0]["id"]) if tv_results else None


# /api/v1/scrobble/
class ScrobbleView(drf_views.APIView):
    """Generic start/pause/stop scrobble events for third-party clients.

    Authenticated the same way as the rest of the API (Bearer/API-Key
    token). "start" only updates the home page's Now Playing card; "pause"
    also saves the resume position; "stop" additionally persists a durable
    progress/status update via the same shared logic the Plex/Jellyfin/Emby
    webhooks use internally. A stop counts as watched at the user's
    threshold (80% by default).
    """

    @extend_schema(
        description=(
            "Record a playback start/pause/stop event from a third-party "
            "client. Movies are identified by tmdb/imdb id; episodes "
            "additionally require season_number/episode_number. Anime "
            "clients may add an anidb id to pin the exact MyAnimeList cour. "
            "'start' only updates the live Now Playing card; 'pause' also "
            "saves the resume position; 'stop' persists a durable "
            "watch/progress update. A stop counts as watched once progress "
            "reaches the user's threshold (scrobble_watched_percent in "
            "/user/preferences/, 80% by default); below it, only the resume "
            "position is kept. Rewatches are recorded as new plays; the same "
            "play sent twice is reported as a duplicate."
        ),
        request={
            "application/json": {
                "type": "object",
                "required": ["action", "media_type", "ids"],
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": list(_ACTIONS),
                    },
                    "media_type": {
                        "type": "string",
                        "enum": list(_MEDIA_TYPES),
                    },
                    "ids": {
                        "type": "object",
                        "description": "At least one of tmdb/imdb/tvdb is required.",
                        "properties": {
                            "tmdb": {"type": "string", "nullable": True},
                            "imdb": {"type": "string", "nullable": True},
                            "tvdb": {"type": "string", "nullable": True},
                            "anidb": {
                                "type": "string",
                                "nullable": True,
                                "description": "Optional, and never sufficient "
                                "on its own. When the user's Anime library "
                                "stores flat MyAnimeList rows, this names the "
                                "exact cour instead of inferring one from the "
                                "season and episode numbers. It selects the "
                                "entry, not the library shape: that follows "
                                "the user's Anime Provider and stays with the "
                                "show once it is tracked.",
                            },
                        },
                    },
                    "title": {"type": "string", "nullable": True},
                    "series_title": {
                        "type": "string",
                        "nullable": True,
                        "description": "Required (in effect) for media_type "
                        "'episode' to power live-card display and title "
                        "search fallback.",
                    },
                    "season_number": {
                        "type": "integer",
                        "nullable": True,
                        "description": "Required for media_type 'episode'.",
                    },
                    "episode_number": {
                        "type": "integer",
                        "nullable": True,
                        "description": "Required for media_type 'episode'.",
                    },
                    "position_seconds": {"type": "integer", "nullable": True},
                    "duration_seconds": {"type": "integer", "nullable": True},
                    "progress": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "nullable": True,
                        "description": "Percent watched. Optional; derived "
                        "from position_seconds/duration_seconds when omitted.",
                    },
                    "completed": {
                        "type": "boolean",
                        "nullable": True,
                        "description": "Only used by 'stop'. Overrides the "
                        "watched threshold when given.",
                    },
                    "played_at": {
                        "type": "string",
                        "format": "date-time",
                        "nullable": True,
                        "description": "Only used by 'stop'. Defaults to the "
                        "exact time the server receives the event.",
                    },
                    "score": {
                        "type": "number",
                        "nullable": True,
                        "description": "Only used by 'stop', for media_type "
                        "'episode'. Sets the user's rating (0-10) on the "
                        "episode.",
                    },
                },
            },
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string"},
                    "action": {
                        "type": "string",
                        "enum": ["start", "pause", "scrobble"],
                        "description": "'scrobble' when a stop counted as "
                        "watched; 'pause' for a pause or a stop below the "
                        "threshold.",
                    },
                    "progress": {"type": "number", "nullable": True},
                    "watched": {"type": "boolean"},
                    "duplicate": {
                        "type": "boolean",
                        "nullable": True,
                        "description": "For a watched movie or episode: "
                        "true when the play matched one already stored and "
                        "nothing new was recorded. Null when not applicable.",
                    },
                },
            },
            400: {
                "type": "object",
                "properties": {"detail": {"type": "string"}},
            },
            404: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string"},
                    "errors": {"type": "string"},
                },
            },
        },
    )
    def post(self, request):
        """Validate and apply a scrobble event."""
        client_event_id = request.headers.get("Idempotency-Key")
        if not client_event_id and isinstance(request.data, dict):
            client_event_id = request.data.get("client_event_id")

        token = request.auth if isinstance(request.auth, IntegrationToken) else None

        def _execute():
            error = _scrobble_request_error(request.data)
            if error:
                return error

            action = request.data.get("action")
            media_type = request.data.get("media_type")
            ids = request.data.get("ids") or {}

            self._update_live_playback(request.user, action, media_type, ids, request.data)

            percent = _progress_percent(request.data)
            position = _position_seconds(request.data, percent)

            if action == "start":
                return _scrobble_response("start", percent)
            if action == "pause":
                self._store_playback_progress(
                    request.user,
                    {
                        "media_type": media_type,
                        "ids": ids,
                        "season_number": request.data.get("season_number"),
                        "episode_number": request.data.get("episode_number"),
                        "position_seconds": position,
                        "duration_seconds": request.data.get("duration_seconds"),
                    },
                    completed=False,
                    create=True,
                )
                return _scrobble_response("pause", percent)

            watched = _is_watched(request.user, request.data, percent)
            raw_played_at = request.data.get("played_at")
            if raw_played_at:
                played_at = try_parse_datetime_input(raw_played_at)
            else:
                # The exact moment, not rounded: CineTrack and other clients
                # compare watch times to the instant.
                played_at = timezone.now() if watched else None
            payload = {
                "media_type": media_type,
                "ids": ids,
                "title": request.data.get("title"),
                "series_title": request.data.get("series_title"),
                "season_number": request.data.get("season_number"),
                "episode_number": request.data.get("episode_number"),
                "position_seconds": position,
                "duration_seconds": request.data.get("duration_seconds"),
                "completed": watched,
                "played_at": played_at,
            }
            processor = GenericScrobbleProcessor()
            try:
                processor.process_payload(payload, request.user)
            except Exception:
                logger.exception("Failed to process generic scrobble payload.")
                return Response(
                    {"detail": "Could not resolve media."},
                    status=HTTP.NOT_FOUND,
                )

            self._store_playback_progress(
                request.user,
                payload,
                completed=is_played(payload),
            )

            if "score" in request.data and media_type == MediaTypes.EPISODE.value:
                self._apply_episode_score(request.user, payload, request.data["score"])

            duplicate = None
            if watched and processor.play_outcome is not None:
                duplicate = processor.play_outcome == PLAY_DUPLICATE
            return _scrobble_response(
                "scrobble" if watched else "pause",
                percent,
                watched=watched,
                duplicate=duplicate,
            )

        if client_event_id:
            response, _ = get_or_record_receipt(
                user=request.user,
                client_event_id=str(client_event_id),
                payload=request.data,
                execute_fn=_execute,
                token=token,
            )
            return response

        return _execute()


    def _apply_episode_score(self, user, payload, raw_score):
        """Set the episode's rating; failures are logged, never raised.

        Validity was already checked in `_scrobble_request_error`; this just
        resolves the already-persisted episode and applies it.
        """
        score, _ = validate_episode_score(raw_score)
        try:
            item = fork_views_playback.resolve_video_item(
                user,
                payload["media_type"],
                payload["ids"],
                payload.get("season_number"),
                payload.get("episode_number"),
                create=False,
            )
            if item is None:
                return
            season = get_tracked_season(user, item.media_id, item.source, item.season_number)
            if season is None:
                return
            apply_episode_score(season, item.episode_number, score)
        except Exception:
            logger.warning("Scrobble episode-score update failed", exc_info=True)

    def _store_playback_progress(self, user, payload, *, completed, create=False):
        """Persist the durable resume position; failures are never raised.

        After a stop the processor has just resolved/created the Item, so this
        is a cheap lookup. A pause may come first, so it may create the
        metadata Item (never a watch row). Exposed to clients via
        /api/v1/playback/progress/.
        """
        position = payload.get("position_seconds")
        if position is None:
            return
        try:
            item = fork_views_playback.resolve_video_item(
                user,
                payload["media_type"],
                payload["ids"],
                payload.get("season_number"),
                payload.get("episode_number"),
                create=create,
            )
            if item is None:
                return
            duration = payload.get("duration_seconds")
            fork_views_playback.upsert_playback_progress(
                user,
                item,
                max(0, int(position)),
                max(0, int(duration)) if duration is not None else None,
                completed=completed,
            )
        except Exception:
            logger.warning("Scrobble playback-progress update failed", exc_info=True)

    def _update_live_playback(self, user, action, media_type, ids, data):
        """Update the Now Playing card; failures are logged, never raised."""
        try:
            source = Sources.TMDB.value
            media_id = _resolve_live_playback_media_id(media_type, ids)
            season_number = data.get("season_number")
            episode_number = data.get("episode_number")
            series_title = data.get("series_title")
            image = None

            if media_type == MediaTypes.EPISODE.value and ids.get("anidb"):
                identity = GenericScrobbleProcessor().resolve_anime_live_identity(
                    user,
                    {
                        "tmdb_id": ids.get("tmdb"),
                        "imdb_id": ids.get("imdb"),
                        "tvdb_id": ids.get("tvdb"),
                        "anidb_id": ids.get("anidb"),
                    },
                    season_number,
                    episode_number,
                )
                if identity:
                    source = identity["source"]
                    media_id = identity["media_id"]
                    season_number = identity["season_number"]
                    episode_number = identity["episode_number"]
                    series_title = identity.get("series_title") or series_title
                    image = identity.get("image")

            live_playback.apply_playback_event(
                user_id=user.id,
                event_type=_EVENT_TYPE_MAP[action],
                playback_media_type=media_type,
                media_id=media_id,
                source=source,
                title=data.get("title"),
                series_title=series_title,
                episode_title=data.get("title")
                if media_type == MediaTypes.EPISODE.value
                else None,
                season_number=season_number,
                episode_number=episode_number,
                view_offset_seconds=data.get("position_seconds"),
                duration_seconds=data.get("duration_seconds"),
                image=image,
            )
        except Exception:
            logger.warning("Scrobble live-playback update failed", exc_info=True)
