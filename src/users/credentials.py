"""Credential management shared by the web settings pages and the API (P1-G).

Named API tokens, add-on install grants, signed-in app installs and the OAuth
apps the user connected. Secrets are returned to the caller once and never
logged.
"""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from api import scopes as api_scopes
from integrations.models import CatalogGrant, IntegrationToken

MAX_TOKEN_NAME_LENGTH = 255


class CredentialError(ValueError):
    """The request cannot be carried out; the message says why."""


def _clean_name(name, missing_message):
    name = str(name or "").strip()[:MAX_TOKEN_NAME_LENGTH]
    if not name:
        raise CredentialError(missing_message)
    return name


def create_integration_token(user, name, scopes, expires_in_days=None):
    """Mint a named, scoped token; return (token, raw secret).

    `scopes` must be known scope names; `expires_in_days` is None for no
    expiry or a whole number of days, at least one.
    """
    name = _clean_name(name, "Give the token a name so you can recognise it later.")
    scopes = list(dict.fromkeys(scopes or []))
    if not scopes:
        msg = "Select at least one permission for the token."
        raise CredentialError(msg)
    unknown = [scope for scope in scopes if scope not in api_scopes.ALL_SCOPES]
    if unknown:
        msg = f"Unknown permission: {', '.join(unknown)}."
        raise CredentialError(msg)

    expires_at = None
    if expires_in_days is not None:
        if isinstance(expires_in_days, bool):
            msg = "Expiry must be a number of days."
            raise CredentialError(msg)
        try:
            days = int(expires_in_days)
        except (TypeError, ValueError) as error:
            msg = "Expiry must be a number of days."
            raise CredentialError(msg) from error
        if days < 1:
            msg = "Expiry must be at least one day."
            raise CredentialError(msg)
        expires_at = timezone.now() + timedelta(days=days)

    return IntegrationToken.generate(
        user=user,
        name=name,
        scopes=scopes,
        expires_at=expires_at,
    )


def revoke_integration_token(user, token_id):
    """Revoke one of the user's live tokens; return it, or None if not theirs."""
    token = IntegrationToken.objects.filter(
        pk=token_id,
        user=user,
        revoked_at__isnull=True,
    ).first()
    if token is not None:
        token.revoked_at = timezone.now()
        token.save(update_fields=["revoked_at"])
    return token


def create_catalog_grant(user, name, *, allow_playback_start=True):
    """Mint an add-on install credential; return (grant, raw token)."""
    name = _clean_name(name, "Give the install a name so you can recognise it.")
    return CatalogGrant.generate(
        user=user,
        name=name,
        allow_playback_start=allow_playback_start,
    )


def revoke_catalog_grant(user, grant_id):
    """Revoke one of the user's live grants; return it, or None if not theirs."""
    grant = CatalogGrant.objects.filter(
        pk=grant_id,
        user=user,
        revoked_at__isnull=True,
    ).first()
    if grant is not None:
        grant.revoked_at = timezone.now()
        grant.save(update_fields=["revoked_at"])
    return grant


def revoke_connected_app(user, client_id):
    """Delete every token and grant the user issued to one OAuth app.

    Returns the app as `connected_apps_for` lists it, or None when the user
    has not connected it.
    """
    from oauth2_provider.models import (
        AccessToken,
        DeviceGrant,
        Grant,
        IDToken,
        RefreshToken,
    )

    from users.views import connected_apps_for

    app = next(
        (app for app in connected_apps_for(user) if app["client_id"] == client_id),
        None,
    )
    if app is None:
        return None
    mine = {"user": user, "application__client_id": client_id}
    with transaction.atomic():
        RefreshToken.objects.filter(**mine).delete()
        AccessToken.objects.filter(**mine).delete()
        IDToken.objects.filter(**mine).delete()
        Grant.objects.filter(**mine).delete()
        DeviceGrant.objects.filter(user=user, client_id=client_id).delete()
    return app


def revoke_app_session(user, session_id):
    """Sign one install out, by an id from `app_sessions_for`.

    Returns the token that was revoked, or None when the id is not one of
    the user's live sessions. The install's history and data are untouched.
    """
    from oauth2_provider.models import AccessToken, RefreshToken

    session_id = str(session_id or "")
    kind, pk = session_id[:1], session_id[1:]
    if not pk.isdigit() or kind not in {"r", "a"}:
        return None
    if kind == "r":
        token = (
            RefreshToken.objects.select_related("application")
            .filter(pk=pk, user=user, revoked__isnull=True)
            .first()
        )
    else:
        token = (
            AccessToken.objects.select_related("application")
            .filter(pk=pk, user=user)
            .first()
        )
    if token is not None:
        # RefreshToken.revoke() also ends its access token.
        token.revoke()
    return token
