"""Account and credential management through the API (P1-G).

Every view here is scoped `NEVER` in `api.scopes`: no token of any kind (named
token, OAuth app, legacy key) may reach it, so a credential can never be used
to mint, widen or revoke credentials. Only a signed-in browser session may,
which the API accepts once the web's session bridge exists (P3).

Secrets (a new token, an add-on install URL) appear once, in the create
response, sent with `Cache-Control: no-store`. List responses never carry
them.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from django.contrib.auth import update_session_auth_hash
from django.urls import reverse
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from api import scopes as api_scopes
from integrations.models import (
    DEFAULT_INTEGRATION_SCOPES,
    CatalogGrant,
    IntegrationToken,
)
from users import credentials as user_credentials
from users.forms import PasswordChangeForm, UserUpdateForm
from users.views import app_sessions_for, connected_apps_for

from .contract_serializers import DetailErrorSerializer

_DEMO_403 = OpenApiResponse(
    DetailErrorSerializer,
    description="Demo accounts are view-only.",
)


def _demo_response(user):
    if user.is_demo:
        return Response(
            {"detail": "This section is view-only for demo accounts."},
            status=HTTP.FORBIDDEN,
        )
    return None


def _secret_response(payload):
    response = Response(payload, status=HTTP.CREATED)
    response["Cache-Control"] = "no-store"
    return response


class FormErrorSerializer(serializers.Serializer):
    """Validation errors per field; `__all__` for the form as a whole."""

    detail = serializers.CharField()
    errors = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


def _form_error_response(form):
    return Response(
        {
            "detail": "The change was not saved.",
            "errors": {field: list(messages) for field, messages in form.errors.items()},
        },
        status=HTTP.BAD_REQUEST,
    )


# --- /api/v1/user/tokens/ ---------------------------------------------------


class IntegrationTokenSerializer(serializers.Serializer):
    """A named API token, without its secret."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    prefix = serializers.CharField(help_text="First characters of the secret.")
    scopes = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)


class ScopeChoiceSerializer(serializers.Serializer):
    """A permission a token can hold."""

    scope = serializers.CharField()
    description = serializers.CharField()
    default = serializers.BooleanField(help_text="Part of the tracking preset.")


class IntegrationTokenListSerializer(serializers.Serializer):
    """The user's live tokens and the permissions a new one can hold."""

    results = IntegrationTokenSerializer(many=True)
    scope_choices = ScopeChoiceSerializer(many=True)


class IntegrationTokenCreateSerializer(serializers.Serializer):
    """A new token."""

    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    expires_in_days = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )


class IntegrationTokenCreatedSerializer(IntegrationTokenSerializer):
    """The new token and its secret, shown this once."""

    secret = serializers.CharField(help_text="Shown once; store it now.")


def _token_payload(token):
    return {
        "id": token.id,
        "name": token.name,
        "prefix": token.token_prefix,
        "scopes": list(token.scopes or []),
        "created_at": token.created_at,
        "last_used_at": token.last_used_at,
        "expires_at": token.expires_at,
    }


class IntegrationTokensView(drf_views.APIView):
    """List or create named, scoped API tokens."""

    @extend_schema(
        operation_id="listIntegrationTokens",
        responses={200: IntegrationTokenListSerializer},
    )
    def get(self, request):
        """Return the live tokens, newest first, without secrets."""
        tokens = IntegrationToken.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
        ).order_by("-created_at")
        return Response(
            {
                "results": [_token_payload(token) for token in tokens],
                "scope_choices": [
                    {
                        "scope": scope,
                        "description": description,
                        "default": scope in DEFAULT_INTEGRATION_SCOPES,
                    }
                    for scope, description in sorted(
                        api_scopes.SCOPE_DESCRIPTIONS.items()
                    )
                ],
            },
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="createIntegrationToken",
        request=IntegrationTokenCreateSerializer,
        responses={
            201: IntegrationTokenCreatedSerializer,
            400: DetailErrorSerializer,
            403: _DEMO_403,
        },
    )
    def post(self, request):
        """Mint the token and return its secret once."""
        if denied := _demo_response(request.user):
            return denied
        data = request.data if isinstance(request.data, dict) else {}
        scopes = data.get("scopes")
        if not isinstance(scopes, list) or not all(isinstance(s, str) for s in scopes):
            return Response(
                {"detail": "scopes must be a list of permission names."},
                status=HTTP.BAD_REQUEST,
            )
        try:
            token, raw_token = user_credentials.create_integration_token(
                request.user,
                data.get("name"),
                scopes,
                expires_in_days=data.get("expires_in_days"),
            )
        except user_credentials.CredentialError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return _secret_response({**_token_payload(token), "secret": raw_token})


class IntegrationTokenDetailView(drf_views.APIView):
    """Revoke one named token."""

    @extend_schema(
        operation_id="revokeIntegrationToken",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, token_id):
        """Revoke the token; apps using it stop working at once."""
        if user_credentials.revoke_integration_token(request.user, token_id) is None:
            return Response({"detail": "Token not found."}, status=HTTP.NOT_FOUND)
        return Response(status=HTTP.NO_CONTENT)


# --- /api/v1/user/catalog-grants/ -------------------------------------------


class CatalogGrantSerializer(serializers.Serializer):
    """An add-on install, without its install URL."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    allow_playback_start = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    last_used_at = serializers.DateTimeField(allow_null=True)


class CatalogGrantListSerializer(serializers.Serializer):
    """The user's live add-on installs."""

    results = CatalogGrantSerializer(many=True)


class CatalogGrantCreateSerializer(serializers.Serializer):
    """A new add-on install."""

    name = serializers.CharField()
    allow_playback_start = serializers.BooleanField(
        required=False,
        help_text="Let the add-on mark an item in progress. Defaults to true.",
    )


class CatalogGrantCreatedSerializer(CatalogGrantSerializer):
    """The new install and its URL, shown this once."""

    manifest_url = serializers.CharField(
        help_text="Add-on install URL; it is the credential. Shown once.",
    )


def _grant_payload(grant):
    return {
        "id": grant.id,
        "name": grant.name,
        "allow_playback_start": grant.allow_playback_start,
        "created_at": grant.created_at,
        "last_used_at": grant.last_used_at,
    }


class CatalogGrantsView(drf_views.APIView):
    """List or create add-on install credentials."""

    @extend_schema(
        operation_id="listCatalogGrants",
        responses={200: CatalogGrantListSerializer},
    )
    def get(self, request):
        """Return the live installs, newest first, without their URLs."""
        grants = CatalogGrant.objects.filter(
            user=request.user,
            revoked_at__isnull=True,
        ).order_by("-created_at")
        return Response(
            {"results": [_grant_payload(grant) for grant in grants]},
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="createCatalogGrant",
        request=CatalogGrantCreateSerializer,
        responses={
            201: CatalogGrantCreatedSerializer,
            400: DetailErrorSerializer,
            403: _DEMO_403,
        },
    )
    def post(self, request):
        """Mint the install and return its URL once."""
        if denied := _demo_response(request.user):
            return denied
        data = request.data if isinstance(request.data, dict) else {}
        allow_playback_start = data.get("allow_playback_start", True)
        if not isinstance(allow_playback_start, bool):
            return Response(
                {"detail": "allow_playback_start must be a boolean."},
                status=HTTP.BAD_REQUEST,
            )
        try:
            grant, token = user_credentials.create_catalog_grant(
                request.user,
                data.get("name"),
                allow_playback_start=allow_playback_start,
            )
        except user_credentials.CredentialError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return _secret_response(
            {
                **_grant_payload(grant),
                "manifest_url": request.build_absolute_uri(
                    reverse("stremio_addon_manifest", args=[token]),
                ),
            },
        )


class CatalogGrantDetailView(drf_views.APIView):
    """Revoke one add-on install."""

    @extend_schema(
        operation_id="revokeCatalogGrant",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, grant_id):
        """Revoke the install; its URL stops working at once."""
        if user_credentials.revoke_catalog_grant(request.user, grant_id) is None:
            return Response({"detail": "Install not found."}, status=HTTP.NOT_FOUND)
        return Response(status=HTTP.NO_CONTENT)


# --- /api/v1/user/connected-apps/ and /api/v1/user/app-sessions/ -------------


class ConnectedAppSerializer(serializers.Serializer):
    """An OAuth app the user signed in to."""

    client_id = serializers.CharField()
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    connected_at = serializers.DateTimeField()


class AppSessionSerializer(serializers.Serializer):
    """One signed-in install of an app."""

    id = serializers.CharField(help_text="Pass to DELETE user/app-sessions/{id}/.")
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    last_active = serializers.DateTimeField()


class ConnectedAppsSerializer(serializers.Serializer):
    """Connected OAuth apps and their signed-in installs."""

    apps = ConnectedAppSerializer(many=True)
    sessions = AppSessionSerializer(many=True)


class ConnectedAppsView(drf_views.APIView):
    """The OAuth apps the user connected and each signed-in install."""

    @extend_schema(
        operation_id="listConnectedApps",
        responses={200: ConnectedAppsSerializer},
    )
    def get(self, request):
        """Return apps and installs, newest first."""
        return Response(
            {
                "apps": connected_apps_for(request.user),
                "sessions": app_sessions_for(request.user),
            },
            status=HTTP.OK,
        )


class ConnectedAppDetailView(drf_views.APIView):
    """Disconnect one OAuth app."""

    @extend_schema(
        operation_id="disconnectApp",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, client_id):
        """Delete every token and grant issued to the app; every install signs out."""
        if user_credentials.revoke_connected_app(request.user, client_id) is None:
            return Response({"detail": "App not connected."}, status=HTTP.NOT_FOUND)
        return Response(status=HTTP.NO_CONTENT)


class AppSessionDetailView(drf_views.APIView):
    """Sign one install out."""

    @extend_schema(
        operation_id="signOutAppSession",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, session_id):
        """Sign the install out; other installs and apps keep working."""
        if user_credentials.revoke_app_session(request.user, session_id) is None:
            return Response({"detail": "Session not found."}, status=HTTP.NOT_FOUND)
        return Response(status=HTTP.NO_CONTENT)


# --- /api/v1/user/account/ and /api/v1/user/password/ ------------------------


class AccountSerializer(serializers.Serializer):
    """Account identity."""

    username = serializers.CharField()
    authenticator_enabled = serializers.BooleanField(
        help_text="Whether recovery by authenticator code is set up.",
    )


class AccountUpdateSerializer(serializers.Serializer):
    """New username."""

    username = serializers.CharField()


class PasswordChangeRequestSerializer(serializers.Serializer):
    """Current password and the new one twice."""

    old_password = serializers.CharField()
    new_password1 = serializers.CharField()
    new_password2 = serializers.CharField()


def _account_payload(user):
    return {
        "username": user.username,
        "authenticator_enabled": bool(user.has_authenticator_configured),
    }


class AccountView(drf_views.APIView):
    """Read the account, or change the username."""

    @extend_schema(operation_id="getAccount", responses={200: AccountSerializer})
    def get(self, request):
        """Return the username and recovery setup."""
        return Response(_account_payload(request.user), status=HTTP.OK)

    @extend_schema(
        operation_id="updateAccount",
        request=AccountUpdateSerializer,
        responses={200: AccountSerializer, 400: FormErrorSerializer},
    )
    def patch(self, request):
        """Change the username, with the web form's checks."""
        data = request.data if isinstance(request.data, dict) else {}
        form = UserUpdateForm(
            {"username": data.get("username", "")},
            instance=request.user,
        )
        if not form.is_valid():
            return _form_error_response(form)
        form.save()
        return Response(_account_payload(request.user), status=HTTP.OK)


class PasswordChangeView(drf_views.APIView):
    """Change the password; the session stays signed in."""

    @extend_schema(
        operation_id="changePassword",
        request=PasswordChangeRequestSerializer,
        responses={204: None, 400: FormErrorSerializer},
    )
    def post(self, request):
        """Check the current password and the new one, then save it."""
        data = request.data if isinstance(request.data, dict) else {}
        form = PasswordChangeForm(
            user=request.user,
            data={
                field: str(data.get(field) or "")
                for field in ("old_password", "new_password1", "new_password2")
            },
        )
        if not form.is_valid():
            return _form_error_response(form)
        user = form.save()
        update_session_auth_hash(request._request, user)
        return Response(status=HTTP.NO_CONTENT)
