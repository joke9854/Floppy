"""App sign-in: Floppy as an OAuth 2.0 / OpenID Connect provider.

The protocol side (authorize, token, refresh, revoke, device flow, discovery) is
django-oauth-toolkit, configured in ``settings.OAUTH2_PROVIDER``. Accounts stay
with allauth: the authorize and device pages send anyone not signed in to
allauth's login page and continue afterwards.

Access tokens authenticate ``/api/v1/`` through
:func:`api.authentication.authenticate_token` and are enforced by ``HasScope``
exactly like a scoped ``IntegrationToken``.
"""

import json

from django.http import JsonResponse
from django.urls import path, reverse
from oauth2_provider import urls as toolkit_urls
from oauth2_provider.models import Application
from oauth2_provider.scopes import BaseScopes
from oauth2_provider.views import AuthorizationView, DeviceAuthorizationView

from api.scopes import APP_SCOPES, OAUTH_SCOPES


class AppScopes(BaseScopes):
    """Every app may ask for ``APP_SCOPES`` and nothing else.

    ``user:read`` and the broader scopes stay with named ``IntegrationToken``
    credentials, which the user creates and limits by hand.
    """

    def get_all_scopes(self):
        """Return every scope with its consent-page description."""
        return OAUTH_SCOPES

    def get_available_scopes(self, application=None, request=None, *args, **kwargs):
        """Return the scopes an app may request."""
        return list(APP_SCOPES)

    def get_default_scopes(self, application=None, request=None, *args, **kwargs):
        """Return the scopes granted when the app does not name any."""
        return list(APP_SCOPES)


class AppAuthorizationView(AuthorizationView):
    """Authorization endpoint that always asks the user for consent.

    The toolkit lets a request carry ``approval_prompt=auto`` to skip the
    consent page once the app holds a token; Floppy always shows it.
    """

    def get(self, request, *args, **kwargs):
        """Drop ``approval_prompt`` before the toolkit reads it."""
        if "approval_prompt" in request.GET:
            request.GET = request.GET.copy()
            request.GET.pop("approval_prompt")
        return super().get(request, *args, **kwargs)


def _oauth_error(error, description, status=400):
    """Return an RFC 6749 section 5.2 error response."""
    response = JsonResponse(
        {"error": error, "error_description": description},
        status=status,
    )
    response["Cache-Control"] = "no-store"
    return response


class AppDeviceAuthorizationView(DeviceAuthorizationView):
    """Device authorization limited to device apps and the app scopes.

    The toolkit's endpoint neither checks that the app is registered for the
    device grant nor validates the requested scopes, so both are checked here
    before a device code exists. It also only knows a fixed verification URI
    from settings, which cannot name the host a self-hosted server is reached
    on, so the URLs are rewritten for the request's host.
    """

    def post(self, request, *args, **kwargs):
        """Validate the app and scopes, then answer with absolute URLs."""
        app = Application.objects.filter(
            client_id=request.POST.get("client_id", ""),
        ).first()
        if app is None:
            return _oauth_error("invalid_client", "Unknown client.", status=401)
        if not app.allows_grant_type(Application.GRANT_DEVICE_CODE):
            return _oauth_error(
                "unauthorized_client",
                "This app may not use the device flow.",
            )
        requested = request.POST.get("scope", "").split()
        if not set(requested) <= set(APP_SCOPES):
            return _oauth_error("invalid_scope", "A requested scope is not allowed.")

        response = super().post(request, *args, **kwargs)
        if response.status_code != 200:  # noqa: PLR2004
            return response
        body = json.loads(response.content)
        page = request.build_absolute_uri(reverse("oauth2_provider:device"))
        body["verification_uri"] = page
        body["verification_uri_complete"] = f"{page}?user_code={body['user_code']}"
        rewritten = JsonResponse(body, status=response.status_code)
        for header, value in response.items():
            if header.lower() != "content-length":
                rewritten[header] = value
        return rewritten


def _replace(patterns, name, view):
    """Return ``patterns`` with the route called ``name`` served by ``view``."""
    return [
        path(str(pattern.pattern), view, name=name) if pattern.name == name else pattern
        for pattern in patterns
    ]


# Mounted at /o/. Application management and dynamic client registration are
# left out: the built-in apps are seeded by migration, and only admins add more.
# RP-initiated logout is left out too; signing out of Floppy stays on the site.
oauth_urlpatterns = [
    *_replace(
        _replace(
            toolkit_urls.base_urlpatterns,
            "authorize",
            AppAuthorizationView.as_view(),
        ),
        "device-authorization",
        AppDeviceAuthorizationView.as_view(),
    ),
    *toolkit_urls.metadata_urlpatterns,
    *[
        pattern
        for pattern in toolkit_urls.oidc_urlpatterns
        if pattern.name != "rp-initiated-logout"
    ],
]
