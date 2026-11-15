"""Trakt and MDBList list imports through the API (P1-E).

The web's `trakt_lists_*` and `mdblist_*` views. Trakt authorizes with the
device-code flow, which needs no redirect URI: the client shows the code
and polls. The device code itself stays on the server. Stored secrets
(Trakt client secret, MDBList API key) are never returned.
"""

import logging
from datetime import timedelta
from http import HTTPStatus as HTTP  # noqa: N814

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from integrations.imports import helpers as import_helpers
from integrations.imports import trakt as trakt_imports
from integrations.models import MDBListAccount, TraktAccount
from lists import tasks as list_tasks
from lists.imports import mdblist as mdblist_imports
from lists.views_helpers import _get_trakt_credentials
from lists.views_mdblist import (
    FREQUENCY_CRONTABS,
    _ensure_mdblist_schedule,
    _remove_mdblist_schedule,
)

from .contract_serializers import DetailErrorSerializer, TaskQueuedSerializer
from .provider_errors import (
    PROVIDER_UNAVAILABLE_DETAIL,
    is_provider_failure,
    provider_unavailable_response,
)

logger = logging.getLogger(__name__)

_PROVIDER_503 = OpenApiResponse(
    DetailErrorSerializer,
    description=(
        f"{PROVIDER_UNAVAILABLE_DETAIL} Code `provider_unavailable`, with "
        "`Retry-After`."
    ),
)


def _device_cache_key(user_id):
    return f"api_trakt_lists_device:{user_id}"


def _pending_device(user_id):
    """Return the pending device authorization, or None if gone or expired."""
    state = cache.get(_device_cache_key(user_id))
    if not isinstance(state, dict):
        return None
    expires_at = parse_datetime(state.get("expires_at") or "")
    if expires_at is None or timezone.now() >= expires_at:
        cache.delete(_device_cache_key(user_id))
        return None
    return state


def _caused_by_unreachable_provider(error):
    """Return True when a MediaImportError hides a network or server failure."""
    cause = error.__cause__ or error.__context__
    if cause is None or not is_provider_failure(cause):
        return False
    status = getattr(cause, "status_code", None)
    if status is None:
        status = getattr(getattr(cause, "response", None), "status_code", None)
    return status is None or status >= HTTP.INTERNAL_SERVER_ERROR


# --- /api/v1/lists/imports/ -------------------------------------------------


class TraktListImportStatusSerializer(serializers.Serializer):
    """Trakt list import setup."""

    has_credentials = serializers.BooleanField()
    authorization_pending = serializers.BooleanField()


class MDBListStatusSerializer(serializers.Serializer):
    """MDBList connection."""

    connected = serializers.BooleanField()
    sync_frequency = serializers.CharField(allow_null=True)
    connection_broken = serializers.BooleanField()
    last_error_message = serializers.CharField(allow_blank=True)
    last_sync_at = serializers.DateTimeField(allow_null=True)


class ListImportStatusSerializer(serializers.Serializer):
    """State of the list import services."""

    trakt = TraktListImportStatusSerializer()
    mdblist = MDBListStatusSerializer()


class ListImportStatusView(drf_views.APIView):
    """Whether Trakt and MDBList list imports are set up."""

    @extend_schema(
        operation_id="getListImportStatus",
        responses={200: ListImportStatusSerializer},
    )
    def get(self, request):
        """Return the import setup, without any stored secret."""
        mdblist = MDBListAccount.objects.filter(user=request.user).first()
        return Response(
            {
                "trakt": {
                    "has_credentials": _get_trakt_credentials(request.user) is not None,
                    "authorization_pending": _pending_device(request.user.id)
                    is not None,
                },
                "mdblist": {
                    "connected": mdblist is not None,
                    "sync_frequency": mdblist.sync_frequency if mdblist else None,
                    "connection_broken": bool(mdblist and mdblist.connection_broken),
                    "last_error_message": (
                        mdblist.last_error_message if mdblist else ""
                    ),
                    "last_sync_at": mdblist.last_sync_at if mdblist else None,
                },
            },
            status=HTTP.OK,
        )


# --- /api/v1/lists/imports/trakt/credentials/ -------------------------------


class TraktCredentialsRequestSerializer(serializers.Serializer):
    """The user's own Trakt API application."""

    client_id = serializers.CharField()
    client_secret = serializers.CharField()


class TraktListCredentialsView(drf_views.APIView):
    """Store the Trakt application used for list imports."""

    @extend_schema(
        operation_id="setTraktListCredentials",
        request=TraktCredentialsRequestSerializer,
        responses={204: None, 400: DetailErrorSerializer},
    )
    def put(self, request):
        """Save the client id and secret, encrypted."""
        data = request.data if isinstance(request.data, dict) else {}
        client_id = str(data.get("client_id") or "").strip()
        client_secret = str(data.get("client_secret") or "").strip()
        if not client_id or not client_secret:
            return Response(
                {"detail": "Trakt client ID and secret are required."},
                status=HTTP.BAD_REQUEST,
            )
        TraktAccount.objects.update_or_create(
            user=request.user,
            defaults={
                "client_id": import_helpers.encrypt(client_id),
                "client_secret": import_helpers.encrypt(client_secret),
            },
        )
        cache.delete(_device_cache_key(request.user.id))
        return Response(status=HTTP.NO_CONTENT)


# --- /api/v1/lists/imports/trakt/device/ ------------------------------------


class TraktDeviceCodeSerializer(serializers.Serializer):
    """What to show the user while they authorize on Trakt."""

    user_code = serializers.CharField()
    verification_url = serializers.CharField()
    interval = serializers.IntegerField(help_text="Seconds between polls.")
    expires_in = serializers.IntegerField(help_text="Seconds until the code expires.")


class TraktDevicePollSerializer(serializers.Serializer):
    """`pending` until the user authorizes, then `importing`."""

    status = serializers.ChoiceField(choices=["pending", "importing"])
    interval = serializers.IntegerField(required=False)
    task_id = serializers.CharField(required=False)


class TraktListDeviceView(drf_views.APIView):
    """Start Trakt authorization for list imports with a device code."""

    @extend_schema(
        operation_id="startTraktListAuthorization",
        request=None,
        responses={
            200: TraktDeviceCodeSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="No Trakt credentials, or Trakt rejected the client ID.",
            ),
            503: _PROVIDER_503,
        },
    )
    def post(self, request):
        """Ask Trakt for a device code and return the code to show."""
        credentials = _get_trakt_credentials(request.user)
        if not credentials:
            return Response(
                {"detail": "Add your Trakt client ID and secret before authorizing."},
                status=HTTP.BAD_REQUEST,
            )
        client_id, _client_secret = credentials
        try:
            device = trakt_imports.request_device_code(client_id=client_id)
        except import_helpers.MediaImportError as error:
            if _caused_by_unreachable_provider(error):
                return provider_unavailable_response()
            return Response(
                {"detail": "Trakt rejected the client ID. Check your Trakt application."},
                status=HTTP.BAD_REQUEST,
            )
        expires_in = int(device["expires_in"])
        cache.set(
            _device_cache_key(request.user.id),
            {
                "device_code": device["device_code"],
                "interval": device["interval"],
                "expires_at": (
                    timezone.now() + timedelta(seconds=expires_in)
                ).isoformat(),
            },
            timeout=expires_in,
        )
        return Response(
            {
                "user_code": device["user_code"],
                "verification_url": device["verification_url"],
                "interval": device["interval"],
                "expires_in": expires_in,
            },
            status=HTTP.OK,
        )


class TraktListDevicePollView(drf_views.APIView):
    """Poll once; when authorized, queue the import of the user's Trakt lists."""

    @extend_schema(
        operation_id="pollTraktListAuthorization",
        request=None,
        responses={
            200: TraktDevicePollSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="Authorization was denied, used or refused. Start again.",
            ),
            410: OpenApiResponse(
                DetailErrorSerializer,
                description="No authorization is pending, or its code expired.",
            ),
            503: _PROVIDER_503,
        },
    )
    def post(self, request):
        """Return pending, or importing with the import task id."""
        state = _pending_device(request.user.id)
        if state is None:
            return Response(
                {
                    "detail": "No Trakt authorization is pending. Start again.",
                    "code": "expired",
                },
                status=HTTP.GONE,
            )
        credentials = _get_trakt_credentials(request.user)
        if not credentials:
            cache.delete(_device_cache_key(request.user.id))
            return Response(
                {"detail": "Trakt credentials are missing. Add them and start again."},
                status=HTTP.BAD_REQUEST,
            )
        client_id, client_secret = credentials
        try:
            result = trakt_imports.poll_device_token(
                state["device_code"],
                client_id=client_id,
                client_secret=client_secret,
            )
        except import_helpers.MediaImportError as error:
            if _caused_by_unreachable_provider(error):
                # Keep the pending code: the next poll may reach Trakt.
                return provider_unavailable_response()
            cache.delete(_device_cache_key(request.user.id))
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        if result is None:
            return Response(
                {"status": "pending", "interval": state["interval"]},
                status=HTTP.OK,
            )
        cache.delete(_device_cache_key(request.user.id))
        task = list_tasks.import_trakt_lists_task.delay(
            request.user.id,
            result["access_token"],
            client_id=client_id,
        )
        return Response({"status": "importing", "task_id": task.id}, status=HTTP.OK)


# --- /api/v1/lists/imports/mdblist/ -----------------------------------------


class MDBListConnectRequestSerializer(serializers.Serializer):
    """The user's MDBList API key and how often to sync."""

    api_key = serializers.CharField()
    sync_frequency = serializers.ChoiceField(
        choices=list(FREQUENCY_CRONTABS),
        required=False,
        help_text="Defaults to `24h`.",
    )


class MDBListReferenceRequestSerializer(serializers.Serializer):
    """A public MDBList list."""

    list_reference = serializers.CharField(help_text="List URL or ID.")


_NOT_CONNECTED = {"detail": "Connect your MDBList account first."}


class MDBListConnectionView(drf_views.APIView):
    """Connect or disconnect MDBList list imports."""

    @extend_schema(
        operation_id="connectMDBList",
        request=MDBListConnectRequestSerializer,
        responses={
            202: TaskQueuedSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="Missing or invalid API key, or unknown sync frequency.",
            ),
            503: _PROVIDER_503,
        },
    )
    def put(self, request):
        """Validate and store the key, schedule syncs, queue the first import."""
        data = request.data if isinstance(request.data, dict) else {}
        api_key = str(data.get("api_key") or "").strip()
        sync_frequency = str(data.get("sync_frequency") or "24h")
        if not api_key:
            return Response(
                {"detail": "An MDBList API key is required."},
                status=HTTP.BAD_REQUEST,
            )
        if sync_frequency not in FREQUENCY_CRONTABS:
            return Response(
                {"detail": f"sync_frequency must be one of {', '.join(FREQUENCY_CRONTABS)}."},
                status=HTTP.BAD_REQUEST,
            )
        try:
            mdblist_imports.validate_api_key(api_key)
        except import_helpers.MediaImportError:
            return Response(
                {"detail": "MDBList API key is invalid or revoked."},
                status=HTTP.BAD_REQUEST,
            )
        except Exception as error:
            if not is_provider_failure(error):
                raise
            return provider_unavailable_response()
        account, _ = MDBListAccount.objects.update_or_create(
            user=request.user,
            defaults={
                "api_key": import_helpers.encrypt(api_key),
                "sync_frequency": sync_frequency,
                "connection_broken": False,
                "last_error_message": "",
            },
        )
        _ensure_mdblist_schedule(request.user, account)
        task = list_tasks.import_mdblist_lists_task.delay(request.user.id)
        return Response({"task_id": task.id}, status=HTTP.ACCEPTED)

    @extend_schema(
        operation_id="disconnectMDBList",
        request=None,
        responses={204: None},
    )
    def delete(self, request):
        """Remove the key and the recurring sync; imported lists stay."""
        _remove_mdblist_schedule(request.user)
        MDBListAccount.objects.filter(user=request.user).delete()
        return Response(status=HTTP.NO_CONTENT)


class MDBListSyncView(drf_views.APIView):
    """Sync the user's MDBList lists now."""

    @extend_schema(
        operation_id="syncMDBListNow",
        request=None,
        responses={202: TaskQueuedSerializer, 404: DetailErrorSerializer},
    )
    def post(self, request):
        """Clear a broken-connection flag and queue the sync."""
        account = MDBListAccount.objects.filter(user=request.user).first()
        if account is None:
            return Response(_NOT_CONNECTED, status=HTTP.NOT_FOUND)
        if account.connection_broken:
            account.connection_broken = False
            account.last_error_message = ""
            account.save(update_fields=["connection_broken", "last_error_message"])
        _ensure_mdblist_schedule(request.user, account)
        task = list_tasks.import_mdblist_lists_task.delay(request.user.id)
        return Response({"task_id": task.id}, status=HTTP.ACCEPTED)


class MDBListImportListView(drf_views.APIView):
    """Import one public MDBList list by URL or ID."""

    @extend_schema(
        operation_id="importMDBListList",
        request=MDBListReferenceRequestSerializer,
        responses={
            202: TaskQueuedSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def post(self, request):
        """Queue the import."""
        data = request.data if isinstance(request.data, dict) else {}
        reference = str(data.get("list_reference") or "").strip()
        if not reference:
            return Response(
                {"detail": "Provide an MDBList list URL or ID."},
                status=HTTP.BAD_REQUEST,
            )
        if not MDBListAccount.objects.filter(user=request.user).exists():
            return Response(_NOT_CONNECTED, status=HTTP.NOT_FOUND)
        task = list_tasks.import_mdblist_list_by_reference_task.delay(
            request.user.id,
            reference,
        )
        return Response({"task_id": task.id}, status=HTTP.ACCEPTED)
