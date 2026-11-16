"""Plex webhook shares and webhook filters, shared by the web and the API.

An owner with Plex connected can let another Floppy user receive the Plex
plays of chosen Plex usernames (and libraries). The recipient turns a
share on or off.
"""

from django.contrib.auth import get_user_model

from integrations.connections import plex_library_values
from integrations.models import PlexWebhookShare


class PlexShareError(ValueError):
    """The change cannot be made; the message says why."""


class PlexShareNotFoundError(PlexShareError):
    """No such share for this user."""


def _plex_account(user):
    account = getattr(user, "plex_account", None)
    return account if account and account.plex_token else None


def clean_usernames(raw_usernames):
    """Return Plex usernames, trimmed and deduplicated case-insensitively."""
    usernames = []
    seen = set()
    for username in raw_usernames:
        username = str(username or "").strip()  # noqa: PLW2901
        if username and username.casefold() not in seen:
            seen.add(username.casefold())
            usernames.append(username)
    return usernames


def share_recipients(owner):
    """Users an owner may share with: active, real accounts other than theirs."""
    return (
        get_user_model()
        .objects.filter(is_active=True, is_demo=False, is_test_account=False)
        .exclude(pk=owner.pk)
        .order_by("username")
    )


def save_share(owner, *, usernames, libraries, share_id=None, recipient_id=None):
    """Create a share (recipient_id) or update one (share_id); return it.

    `libraries` is a list of `machine::section` keys, or None for all.
    """
    plex_account = _plex_account(owner)
    if plex_account is None:
        msg = "Connect Plex before sharing its webhook."
        raise PlexShareError(msg)

    if share_id is not None:
        share = (
            PlexWebhookShare.objects.select_related("recipient")
            .filter(pk=share_id, owner=owner)
            .first()
        )
        if share is None:
            msg = "Share not found."
            raise PlexShareNotFoundError(msg)
    else:
        recipient = (
            get_user_model()
            .objects.filter(
                pk=recipient_id,
                is_active=True,
                is_demo=False,
                is_test_account=False,
            )
            .first()
            if recipient_id is not None
            else None
        )
        if recipient is None:
            msg = "Recipient not found."
            raise PlexShareNotFoundError(msg)
        if recipient == owner:
            msg = "You cannot share a Plex webhook with yourself."
            raise PlexShareError(msg)
        share = PlexWebhookShare(owner=owner, recipient=recipient)

    usernames = clean_usernames(usernames)
    if not usernames:
        msg = "Enter one or more Plex usernames for this share."
        raise PlexShareError(msg)
    wanted = {username.casefold() for username in usernames}
    for existing in (
        PlexWebhookShare.objects.filter(owner=owner)
        .exclude(pk=share.pk or None)
        .values_list("plex_username", flat=True)
    ):
        taken = {name.strip().casefold() for name in existing.split(",") if name.strip()}
        if wanted & taken:
            msg = (
                "One or more Plex usernames are already assigned to another "
                "shared profile."
            )
            raise PlexShareError(msg)

    if libraries is not None:
        libraries = list(dict.fromkeys(str(value).strip() for value in libraries))
        libraries = [value for value in libraries if value]
        if set(libraries) - plex_library_values(plex_account):
            msg = "One or more selected Plex libraries are invalid."
            raise PlexShareError(msg)

    share.plex_username = ", ".join(usernames)
    share.allowed_libraries = libraries
    share.save()
    return share


def set_share_enabled(recipient, share_id, *, enabled):
    """Turn a received share on or off; return it."""
    share = (
        PlexWebhookShare.objects.select_related("owner")
        .filter(pk=share_id, recipient=recipient)
        .first()
    )
    if share is None:
        msg = "Share not found."
        raise PlexShareNotFoundError(msg)
    if enabled and _plex_account(share.owner) is None:
        msg = "The Plex owner is not currently connected."
        raise PlexShareError(msg)
    share.recipient_enabled = enabled
    share.save(update_fields=["recipient_enabled", "updated_at"])
    return share


def delete_share(owner, share_id):
    """Revoke one of the owner's shares; return the recipient's username."""
    share = (
        PlexWebhookShare.objects.select_related("recipient")
        .filter(pk=share_id, owner=owner)
        .first()
    )
    if share is None:
        msg = "Share not found."
        raise PlexShareNotFoundError(msg)
    recipient_name = share.recipient.username
    share.delete()
    return recipient_name


def save_webhook_libraries(user, libraries):
    """Store which Plex libraries the webhook accepts; return the saved list.

    Unknown libraries are dropped when the account's libraries are known.
    """
    cleaned = [value for value in dict.fromkeys(str(v).strip() for v in libraries) if value]
    valid = plex_library_values(getattr(user, "plex_account", None))
    if valid:
        cleaned = [value for value in cleaned if value in valid]
    user.plex_webhook_libraries = cleaned
    user.save(update_fields=["plex_webhook_libraries"])
    return cleaned
