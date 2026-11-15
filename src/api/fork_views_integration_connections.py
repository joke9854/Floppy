"""Connect, disconnect and run integrations through the API (P1-H).

The web's Import and Integrations settings for services connected with a
key, a token or a password. OAuth and device-code sign-ins (Plex, Trakt,
Simkl, AniList, Storyteller) stay web pages; the screens link to them.

Connecting, disconnecting and changing settings store or remove another
service's credentials, so no token may (scope `NEVER`): only a signed-in
session. Status, imports and polls use the imports scopes. Responses never
include a stored secret.

Errors: 400 with `detail` for bad credentials or input; 503 code
`integration_unreachable` with `Retry-After` when the other service could
not be reached; 409 code `not_connected` or `already_running`.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from integrations import connections
from integrations.models import RadarrInstance, SonarrInstance

from .contract_serializers import DetailErrorSerializer

UNREACHABLE_RETRY_SECONDS = 30
CONSOLE_DEFAULT_TIME = "04:00"

# --- Status ------------------------------------------------------------------

# Non-secret fields shown per service: account relation -> fields.
_DETAIL_FIELDS = {
    "jellyfin": (
        "jellyfin_account",
        (
            "base_url",
            "jellyfin_username",
            "push_watched_enabled",
            "push_unwatched_enabled",
            "scheduled_push_enabled",
            "instant_push_enabled",
            "pull_history_enabled",
            "playback_reporting_available",
            "last_pull_at",
            "last_pull_error_message",
        ),
    ),
    "plex": (
        "plex_account",
        (
            "plex_username",
            "server_name",
            "watchlist_sync_enabled",
            "watchlist_last_synced_at",
            "watchlist_last_error",
        ),
    ),
    "audiobookshelf": ("audiobookshelf_account", ("base_url",)),
    "storyteller": ("storyteller_account", ("server_url",)),
    "koreader": (
        "koreader_account",
        (
            "server_url",
            "username",
            "verify_ssl",
            "create_missing",
            "skip_finished_books",
            "finished_threshold",
        ),
    ),
    "stremio": ("stremio_account", ()),
    "xbox": ("xbox_account", ("gamertag",)),
    "psn": ("psn_account", ("online_id",)),
    "pocketcasts": ("pocketcasts_account", ("token_expires_at",)),
    "gpodder": ("gpodder_account", ("device_filter",)),
    "lastfm": (
        "lastfm_account",
        (
            "lastfm_username",
            "history_import_status",
            "history_import_next_page",
            "history_import_total_pages",
            "history_import_last_error_message",
        ),
    ),
    "koito": (
        "koito_account",
        ("base_url", "history_import_status", "history_import_last_error_message"),
    ),
}

_INSTANCE_MODELS = {"radarr": RadarrInstance, "sonarr": SonarrInstance}


def _related(user, attribute):
    try:
        return getattr(user, attribute)
    except ObjectDoesNotExist:
        return None


def _fresh(user):
    """Reload the user so one-to-one account caches are current."""
    return type(user).objects.get(pk=user.pk)


def _is_connected(service, account):
    if service == "plex":
        return bool(account.plex_token)
    return bool(getattr(account, "is_connected", True))


def _service_status(user, service):
    attribute, fields = _DETAIL_FIELDS[service]
    account = _related(user, attribute)
    if account is None:
        return {
            "service": service,
            "connected": False,
            "connection_broken": False,
            "last_error_message": "",
            "last_sync_at": None,
            "details": {},
        }
    return {
        "service": service,
        "connected": _is_connected(service, account),
        "connection_broken": bool(getattr(account, "connection_broken", False)),
        "last_error_message": getattr(account, "last_error_message", "") or "",
        "last_sync_at": getattr(account, "last_sync_at", None),
        "details": {field: getattr(account, field) for field in fields},
    }


def _instance_payload(instance):
    return {
        "id": instance.id,
        "name": instance.name or "",
        "base_url": instance.base_url,
        "connected": bool(instance.is_connected),
        "connection_broken": instance.connection_broken,
        "last_error_message": instance.last_error_message or "",
        "last_sync_at": instance.last_sync_at,
    }


class IntegrationStatusSerializer(serializers.Serializer):
    """One account-based service."""

    service = serializers.CharField()
    connected = serializers.BooleanField()
    connection_broken = serializers.BooleanField()
    last_error_message = serializers.CharField(allow_blank=True)
    last_sync_at = serializers.DateTimeField(allow_null=True)
    details = serializers.DictField(help_text="Non-secret settings of the service.")


class IntegrationInstanceSerializer(serializers.Serializer):
    """One Radarr or Sonarr server."""

    id = serializers.IntegerField()
    name = serializers.CharField(allow_blank=True)
    base_url = serializers.CharField()
    connected = serializers.BooleanField()
    connection_broken = serializers.BooleanField()
    last_error_message = serializers.CharField(allow_blank=True)
    last_sync_at = serializers.DateTimeField(allow_null=True)


class IntegrationOverviewSerializer(serializers.Serializer):
    """Every integration's connection state."""

    services = IntegrationStatusSerializer(many=True)
    radarr = IntegrationInstanceSerializer(many=True)
    sonarr = IntegrationInstanceSerializer(many=True)


class IntegrationsView(drf_views.APIView):
    """Connection state of every key- or password-based integration."""

    @extend_schema(
        operation_id="listIntegrations",
        responses={200: IntegrationOverviewSerializer},
    )
    def get(self, request):
        """Return each service's state, without secrets."""
        return Response(
            {
                "services": [
                    _service_status(request.user, service) for service in _DETAIL_FIELDS
                ],
                **{
                    service: [
                        _instance_payload(instance)
                        for instance in model.objects.filter(user=request.user).order_by(
                            "created_at"
                        )
                    ]
                    for service, model in _INSTANCE_MODELS.items()
                },
            },
            status=HTTP.OK,
        )


# --- Errors ------------------------------------------------------------------


def _error_response(error):
    """Map an IntegrationError to a response; never echo remote error text."""
    if isinstance(error, connections.AlreadyRunningError):
        return Response(
            {"detail": error.message, "code": "already_running"},
            status=HTTP.CONFLICT,
        )
    if isinstance(error, connections.NotConnectedError):
        return Response(
            {"detail": error.message, "code": "not_connected"},
            status=HTTP.CONFLICT,
        )
    if error.unreachable:
        response = Response(
            {"detail": error.message, "code": "integration_unreachable"},
            status=HTTP.SERVICE_UNAVAILABLE,
        )
        response["Retry-After"] = str(UNREACHABLE_RETRY_SECONDS)
        return response
    return Response({"detail": error.message}, status=HTTP.BAD_REQUEST)


_ERRORS = {
    400: OpenApiResponse(DetailErrorSerializer, description="Bad credentials or input."),
    409: OpenApiResponse(
        DetailErrorSerializer,
        description="Code `not_connected` or `already_running`.",
    ),
    503: OpenApiResponse(
        DetailErrorSerializer,
        description="Code `integration_unreachable`, with `Retry-After`.",
    ),
}


def _data(request):
    return request.data if isinstance(request.data, dict) else {}


def _text(data, field):
    value = data.get(field)
    return value.strip() if isinstance(value, str) else ""


def _flag(data, field, default=False):
    value = data.get(field, default)
    if not isinstance(value, bool):
        msg = f"{field} must be a boolean."
        raise connections.IntegrationError(msg)
    return value


# --- Connect / disconnect ----------------------------------------------------


def _connect_xbox(user, data):
    connections.connect_xbox(user, _text(data, "api_key"))
    connections.start_xbox_import(
        user, mode="new", frequency="once", time=CONSOLE_DEFAULT_TIME
    )


def _connect_psn(user, data):
    connections.connect_psn(user, _text(data, "npsso"))
    connections.start_psn_import(
        user, mode="new", frequency="once", time=CONSOLE_DEFAULT_TIME
    )


def _connect_koreader(user, data):
    connections.connect_koreader(
        user,
        _text(data, "server_url"),
        _text(data, "username"),
        data.get("password") if isinstance(data.get("password"), str) else "",
        verify_ssl=_flag(data, "verify_ssl", default=True),
        create_missing=_flag(data, "create_missing"),
        skip_finished_books=_flag(data, "skip_finished_books"),
        finished_threshold_percent=str(data.get("finished_threshold_percent") or ""),
    )
    connections.queue_koreader_import(user, "new")


# service -> (connect(user, data), disconnect(user), body fields for the docs)
_CONNECTORS = {
    "jellyfin": (
        lambda user, data: connections.connect_jellyfin(
            user, _text(data, "base_url"), _text(data, "api_key"), _text(data, "username")
        ),
        connections.disconnect_jellyfin,
        "base_url, api_key, username (optional)",
    ),
    "audiobookshelf": (
        lambda user, data: connections.connect_audiobookshelf(
            user, _text(data, "base_url"), _text(data, "api_token")
        ),
        connections.disconnect_audiobookshelf,
        "base_url, api_token",
    ),
    "koreader": (
        _connect_koreader,
        connections.disconnect_koreader,
        "server_url, username, password, verify_ssl, create_missing, "
        "skip_finished_books, finished_threshold_percent",
    ),
    "stremio": (
        lambda user, data: connections.connect_stremio(
            user,
            _text(data, "email"),
            data.get("password") if isinstance(data.get("password"), str) else "",
            _text(data, "auth_key"),
        ),
        connections.disconnect_stremio,
        "auth_key, or email and password",
    ),
    "xbox": (_connect_xbox, connections.disconnect_xbox, "api_key (OpenXBL)"),
    "psn": (_connect_psn, connections.disconnect_psn, "npsso"),
    "pocketcasts": (
        lambda user, data: connections.connect_pocketcasts(
            user,
            _text(data, "email"),
            data.get("password") if isinstance(data.get("password"), str) else "",
        ),
        connections.disconnect_pocketcasts,
        "email, password",
    ),
    "gpodder": (
        lambda user, data: connections.connect_gpodder(
            user,
            _text(data, "server_url"),
            _text(data, "username"),
            data.get("password") if isinstance(data.get("password"), str) else "",
            _text(data, "device_filter"),
        ),
        connections.disconnect_gpodder,
        "server_url (optional), username, password, device_filter (optional)",
    ),
    "lastfm": (
        lambda user, data: connections.connect_lastfm(user, _text(data, "username")),
        connections.disconnect_lastfm,
        "username",
    ),
    "koito": (
        lambda user, data: connections.connect_koito(
            user, _text(data, "base_url"), _text(data, "api_key")
        ),
        connections.disconnect_koito,
        "base_url, api_key",
    ),
}
# Signed in on the web (OAuth or device code); only disconnect here.
_DISCONNECT_ONLY = {
    "plex": connections.disconnect_plex,
    "storyteller": connections.disconnect_storyteller,
}

_SERVICE_PARAMETER = OpenApiParameter(
    "service",
    OpenApiTypes.STR,
    OpenApiParameter.PATH,
    enum=sorted(_CONNECTORS),
    description="; ".join(
        f"`{service}`: {fields}" for service, (_c, _d, fields) in _CONNECTORS.items()
    ),
)


class IntegrationConnectionView(drf_views.APIView):
    """Connect or disconnect one service."""

    @extend_schema(
        operation_id="connectIntegration",
        parameters=[_SERVICE_PARAMETER],
        request=OpenApiTypes.OBJECT,
        responses={200: IntegrationStatusSerializer, 404: DetailErrorSerializer, **_ERRORS},
    )
    def put(self, request, service):
        """Check the credentials with the service, store them and start an import."""
        connector = _CONNECTORS.get(service)
        if connector is None:
            return Response(
                {"detail": "Unknown service.", "services": sorted(_CONNECTORS)},
                status=HTTP.NOT_FOUND,
            )
        try:
            connector[0](request.user, _data(request))
        except connections.IntegrationError as error:
            return _error_response(error)
        return Response(_service_status(_fresh(request.user), service), status=HTTP.OK)

    @extend_schema(
        operation_id="disconnectIntegration",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, service):
        """Remove the stored credentials and schedules; imported data stays."""
        disconnect = (
            _CONNECTORS[service][1]
            if service in _CONNECTORS
            else _DISCONNECT_ONLY.get(service)
        )
        if disconnect is None:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        disconnect(request.user)
        return Response(status=HTTP.NO_CONTENT)


# --- Imports and actions -----------------------------------------------------


class IntegrationImportRequestSerializer(serializers.Serializer):
    """Optional import settings."""

    mode = serializers.CharField(
        required=False, help_text="`new` (default) or `overwrite`; koreader, xbox, psn."
    )
    frequency = serializers.ChoiceField(
        choices=["once", "daily", "2days"],
        required=False,
        help_text="xbox and psn: run once (default) or on a schedule.",
    )
    time = serializers.CharField(
        required=False, help_text="xbox and psn schedules: `HH:MM`, default 04:00."
    )


class IntegrationQueuedSerializer(serializers.Serializer):
    """What was started."""

    task_id = serializers.CharField(allow_null=True)
    outcome = serializers.ChoiceField(
        choices=["queued", "scheduled", "reenabled"],
        help_text="`scheduled`/`reenabled`: a recurring import was set up.",
    )


def _queued(result):
    if isinstance(result, connections.ImportQueued):
        return {
            "task_id": getattr(result.result, "id", None),
            "outcome": result.outcome,
        }
    return {"task_id": getattr(result, "id", None), "outcome": "queued"}


def _console_import(start):
    def run(user, data):
        return start(
            user,
            mode=_text(data, "mode") or "new",
            frequency=_text(data, "frequency") or "once",
            time=_text(data, "time") or CONSOLE_DEFAULT_TIME,
        )

    return run


_IMPORTS = {
    "audiobookshelf": lambda user, _data: connections.start_audiobookshelf_import(user),
    "storyteller": lambda user, _data: connections.start_storyteller_import(user),
    "koreader": lambda user, data: connections.start_koreader_import(
        user, _text(data, "mode") or "new"
    ),
    "stremio": lambda user, _data: connections.start_stremio_import(user),
    "xbox": _console_import(connections.start_xbox_import),
    "psn": _console_import(connections.start_psn_import),
    "pocketcasts": lambda user, _data: connections.start_pocketcasts_import(user),
    "gpodder": lambda user, _data: connections.start_gpodder_import(user),
    "lastfm": lambda user, _data: connections.start_lastfm_history_import(user),
    "koito": lambda user, _data: connections.start_koito_history_import(user),
}

_ACTIONS = {
    ("jellyfin", "push"): connections.push_jellyfin_now,
    ("jellyfin", "pull"): connections.pull_jellyfin_now,
    ("lastfm", "poll"): connections.poll_lastfm_now,
    ("koito", "poll"): connections.poll_koito_now,
    ("plex", "disable-watchlist"): connections.disable_plex_watchlist,
}


class IntegrationImportView(drf_views.APIView):
    """Run a service's import now (Last.fm and Koito: the full history)."""

    @extend_schema(
        operation_id="startIntegrationImport",
        request=IntegrationImportRequestSerializer,
        responses={202: IntegrationQueuedSerializer, 404: DetailErrorSerializer, **_ERRORS},
    )
    def post(self, request, service):
        """Queue the import and return its task."""
        start = _IMPORTS.get(service)
        if start is None:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        try:
            result = start(request.user, _data(request))
        except connections.IntegrationError as error:
            return _error_response(error)
        return Response(_queued(result), status=HTTP.ACCEPTED)


class IntegrationActionView(drf_views.APIView):
    """Jellyfin push or pull now, Last.fm or Koito poll now, stop Plex watchlist sync."""

    @extend_schema(
        operation_id="runIntegrationAction",
        request=None,
        responses={202: IntegrationQueuedSerializer, 404: DetailErrorSerializer, **_ERRORS},
    )
    def post(self, request, service, action):
        """Run the action."""
        run = _ACTIONS.get((service, action))
        if run is None:
            return Response({"detail": "Unknown action."}, status=HTTP.NOT_FOUND)
        try:
            result = run(request.user)
        except connections.IntegrationError as error:
            return _error_response(error)
        return Response(_queued(result), status=HTTP.ACCEPTED)


# --- Settings ----------------------------------------------------------------


_JELLYFIN_FLAGS = (
    "push_watched_enabled",
    "push_unwatched_enabled",
    "scheduled_push_enabled",
    "instant_push_enabled",
    "pull_history_enabled",
)


def _jellyfin_settings(user, data):
    account = _related(user, "jellyfin_account")
    if account is None:
        msg = "Connect Jellyfin first."
        raise connections.NotConnectedError(msg)
    connections.update_jellyfin_settings(
        user,
        **{
            flag: _flag(data, flag, default=getattr(account, flag))
            for flag in _JELLYFIN_FLAGS
        },
    )


def _koreader_settings(user, data):
    account = _related(user, "koreader_account")
    if account is None:
        msg = "Connect KOReader first."
        raise connections.NotConnectedError(msg)
    threshold = data.get("finished_threshold_percent")
    connections.update_koreader_settings(
        user,
        _text(data, "server_url") or account.server_url,
        _text(data, "username") or account.username,
        data.get("password") if isinstance(data.get("password"), str) else "",
        verify_ssl=_flag(data, "verify_ssl", default=account.verify_ssl),
        create_missing=_flag(data, "create_missing", default=account.create_missing),
        skip_finished_books=_flag(
            data, "skip_finished_books", default=account.skip_finished_books
        ),
        finished_threshold_percent=(
            str(threshold)
            if threshold is not None
            else str(round(account.finished_threshold * 100, 2))
        ),
    )


_SETTINGS = {"jellyfin": _jellyfin_settings, "koreader": _koreader_settings}


class IntegrationSettingsView(drf_views.APIView):
    """Change Jellyfin or KOReader settings; omitted fields keep their value."""

    @extend_schema(
        operation_id="updateIntegrationSettings",
        request=OpenApiTypes.OBJECT,
        responses={200: IntegrationStatusSerializer, 404: DetailErrorSerializer, **_ERRORS},
    )
    def patch(self, request, service):
        """Save the settings and return the service state.

        Jellyfin: the five push/pull booleans. KOReader: server_url, username,
        password (blank keeps the stored one), verify_ssl, create_missing,
        skip_finished_books, finished_threshold_percent; re-checked with the
        server.
        """
        update = _SETTINGS.get(service)
        if update is None:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        try:
            update(request.user, _data(request))
        except connections.IntegrationError as error:
            return _error_response(error)
        return Response(_service_status(_fresh(request.user), service), status=HTTP.OK)


# --- Radarr / Sonarr instances -----------------------------------------------


class ArrInstanceCreateSerializer(serializers.Serializer):
    """A Radarr or Sonarr server."""

    base_url = serializers.CharField()
    api_key = serializers.CharField()
    name = serializers.CharField(required=False, allow_blank=True)


_ARR = {
    "radarr": (
        connections.connect_radarr,
        connections.disconnect_radarr,
        connections.start_radarr_import,
    ),
    "sonarr": (
        connections.connect_sonarr,
        connections.disconnect_sonarr,
        connections.start_sonarr_import,
    ),
}


class ArrInstancesView(drf_views.APIView):
    """Add a Radarr or Sonarr server."""

    @extend_schema(
        operation_id="addArrInstance",
        request=ArrInstanceCreateSerializer,
        responses={201: IntegrationInstanceSerializer, 404: DetailErrorSerializer, **_ERRORS},
    )
    def post(self, request, service):
        """Check the server, store it and start its first import."""
        if service not in _ARR:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        data = _data(request)
        try:
            instance = _ARR[service][0](
                request.user,
                _text(data, "base_url"),
                _text(data, "api_key"),
                _text(data, "name"),
            )
        except connections.IntegrationError as error:
            return _error_response(error)
        return Response(_instance_payload(instance), status=HTTP.CREATED)


class ArrInstanceDetailView(drf_views.APIView):
    """Remove a Radarr or Sonarr server."""

    @extend_schema(
        operation_id="removeArrInstance",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, service, instance_id):
        """Remove the server, its schedule and its collection state."""
        if service not in _ARR:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        try:
            _ARR[service][1](request.user, instance_id)
        except connections.NotConnectedError:
            return Response({"detail": "Server not found."}, status=HTTP.NOT_FOUND)
        return Response(status=HTTP.NO_CONTENT)


class ArrInstanceImportView(drf_views.APIView):
    """Import from one Radarr or Sonarr server now."""

    @extend_schema(
        operation_id="startArrImport",
        request=None,
        responses={202: IntegrationQueuedSerializer, 404: DetailErrorSerializer},
    )
    def post(self, request, service, instance_id):
        """Queue the import."""
        if service not in _ARR:
            return Response({"detail": "Unknown service."}, status=HTTP.NOT_FOUND)
        try:
            result = _ARR[service][2](request.user, instance_id)
        except connections.NotConnectedError:
            return Response({"detail": "Server not found."}, status=HTTP.NOT_FOUND)
        return Response(_queued(result), status=HTTP.ACCEPTED)
