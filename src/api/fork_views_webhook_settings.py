"""Webhook filters and Plex webhook shares through the API (P1-H follow-up).

Which Plex users and libraries the Plex webhook accepts, how Plex
libraries import, which Jellyfin events apply, and the Seerr webhook
settings. Plex webhook shares let another Floppy user receive chosen Plex
users' plays; granting or accepting one is consent to share data, so the
share endpoints are scoped `NEVER` (session logins only).
"""

from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from integrations.connections import plex_library_values
from integrations.imports.plex_audiobooks import CONTENT_KINDS
from integrations.models import PlexWebhookShare
from users import plex_shares, webhook_settings

from .contract_serializers import DetailErrorSerializer

# --- /api/v1/user/webhook-settings/ -----------------------------------------


class PlexLibrarySerializer(serializers.Serializer):
    """A library of the connected Plex server."""

    value = serializers.CharField(help_text="`machine::section` key.")
    label = serializers.CharField()
    server_name = serializers.CharField(allow_blank=True)
    content_kind = serializers.CharField(help_text="`auto`, `music` or `audiobook`.")


class SeerrSettingsSerializer(serializers.Serializer):
    """Seerr webhook settings."""

    enabled = serializers.BooleanField()
    trigger_statuses = serializers.ListField(
        child=serializers.CharField(),
        help_text="Empty: default behaviour (UNKNOWN is skipped).",
    )
    allowed_usernames = serializers.ListField(child=serializers.CharField())
    default_added_status = serializers.CharField()


class WebhookSettingsSerializer(serializers.Serializer):
    """Webhook filters."""

    plex_usernames = serializers.ListField(child=serializers.CharField())
    plex_webhook_libraries = serializers.ListField(
        child=serializers.CharField(),
        help_text="Libraries the Plex webhook accepts; empty means all.",
    )
    plex_libraries = PlexLibrarySerializer(many=True, read_only=True)
    jellyfin_mark_played_enabled = serializers.BooleanField()
    jellyfin_mark_unplayed_enabled = serializers.BooleanField()
    seerr = SeerrSettingsSerializer()


class WebhookSettingsUpdateSerializer(serializers.Serializer):
    """Fields to change; omitted fields keep their value."""

    plex_usernames = serializers.ListField(child=serializers.CharField(), required=False)
    plex_webhook_libraries = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    plex_content_kinds = serializers.DictField(
        child=serializers.ChoiceField(choices=list(CONTENT_KINDS)),
        required=False,
        help_text="`machine::section` -> how that library imports.",
    )
    jellyfin_mark_played_enabled = serializers.BooleanField(required=False)
    jellyfin_mark_unplayed_enabled = serializers.BooleanField(required=False)
    seerr = SeerrSettingsSerializer(required=False)


def _split(value):
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _plex_libraries(user):
    account = getattr(user, "plex_account", None)
    if not account or not account.plex_token:
        return []
    libraries = []
    for section in account.sections or []:
        machine, section_id = section.get("machine_identifier"), section.get("id")
        if not machine or not section_id:
            continue
        libraries.append(
            {
                "value": f"{machine}::{section_id}",
                "label": section.get("title") or f"Library {section_id}",
                "server_name": section.get("server_name") or "",
                "content_kind": account.content_kind(machine, section_id),
            },
        )
    return libraries


def _settings_payload(user):
    return {
        "plex_usernames": _split(user.plex_usernames),
        "plex_webhook_libraries": list(user.plex_webhook_libraries or []),
        "plex_libraries": _plex_libraries(user),
        "jellyfin_mark_played_enabled": user.jellyfin_mark_played_enabled,
        "jellyfin_mark_unplayed_enabled": user.jellyfin_mark_unplayed_enabled,
        "seerr": {
            # kept: the model fields keep their jellyseerr_* names
            "enabled": user.jellyseerr_enabled,
            "trigger_statuses": _split(user.jellyseerr_trigger_statuses),
            "allowed_usernames": _split(user.jellyseerr_allowed_usernames),
            "default_added_status": user.jellyseerr_default_added_status,
        },
    }


def _bad(detail):
    return Response({"detail": detail}, status=HTTP.BAD_REQUEST)


def _is_text_list(value):
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


class WebhookSettingsView(drf_views.APIView):
    """Read or change webhook filters (Plex, Jellyfin, Seerr)."""

    @extend_schema(
        operation_id="getWebhookSettings",
        responses={200: WebhookSettingsSerializer},
    )
    def get(self, request):
        """Return the filters and the Plex libraries to choose from."""
        return Response(_settings_payload(request.user), status=HTTP.OK)

    @extend_schema(
        operation_id="updateWebhookSettings",
        request=WebhookSettingsUpdateSerializer,
        responses={200: WebhookSettingsSerializer, 400: DetailErrorSerializer},
    )
    def patch(self, request):
        """Save the fields sent."""
        user = request.user
        data = request.data if isinstance(request.data, dict) else {}
        for field in ("plex_usernames", "plex_webhook_libraries"):
            if field in data and not _is_text_list(data[field]):
                return _bad(f"{field} must be a list of strings.")
        for field in ("jellyfin_mark_played_enabled", "jellyfin_mark_unplayed_enabled"):
            if field in data and not isinstance(data[field], bool):
                return _bad(f"{field} must be a boolean.")

        kinds = data.get("plex_content_kinds")
        account = getattr(user, "plex_account", None)
        if kinds is not None:
            valid = plex_library_values(account)
            if not isinstance(kinds, dict) or any(
                key not in valid or kind not in CONTENT_KINDS
                for key, kind in kinds.items()
            ):
                return _bad(
                    "plex_content_kinds maps known libraries to auto, music or "
                    "audiobook.",
                )

        seerr = data.get("seerr")
        if seerr is not None:
            if not isinstance(seerr, dict):
                return _bad("seerr must be an object.")
            current = _settings_payload(user)["seerr"]
            merged = {**current, **seerr}
            if not isinstance(merged["enabled"], bool) or not all(
                _is_text_list(merged[key])
                for key in ("trigger_statuses", "allowed_usernames")
            ):
                return _bad(
                    "seerr.enabled is a boolean; trigger_statuses and "
                    "allowed_usernames are lists of strings.",
                )
            try:
                webhook_settings.save_seerr_settings(
                    user,
                    enabled=merged["enabled"],
                    trigger_statuses=merged["trigger_statuses"],
                    allowed_usernames=merged["allowed_usernames"],
                    default_added_status=str(merged["default_added_status"] or ""),
                )
            except webhook_settings.WebhookSettingsError as error:
                return _bad(str(error))

        if "plex_usernames" in data:
            user.plex_usernames = ", ".join(
                plex_shares.clean_usernames(data["plex_usernames"])
            )
            user.save(update_fields=["plex_usernames"])
        if "plex_webhook_libraries" in data:
            plex_shares.save_webhook_libraries(user, data["plex_webhook_libraries"])
        flags = [
            field
            for field in ("jellyfin_mark_played_enabled", "jellyfin_mark_unplayed_enabled")
            if field in data
        ]
        if flags:
            for field in flags:
                setattr(user, field, data[field])
            user.save(update_fields=flags)
        if kinds:
            changed = False
            for key, kind in kinds.items():
                machine, section_id = key.split("::", 1)
                changed = account.set_content_kind(machine, section_id, kind) or changed
            if changed:
                account.save(update_fields=["section_settings"])
        return Response(_settings_payload(user), status=HTTP.OK)


# --- /api/v1/integrations/plex/shares/ --------------------------------------


class PlexShareSerializer(serializers.Serializer):
    """A Plex webhook share."""

    id = serializers.IntegerField()
    owner = serializers.CharField(help_text="Owner's Floppy username.")
    recipient = serializers.CharField(help_text="Recipient's Floppy username.")
    plex_usernames = serializers.ListField(child=serializers.CharField())
    allowed_libraries = serializers.ListField(
        child=serializers.CharField(),
        allow_null=True,
        help_text="null: every library.",
    )
    recipient_enabled = serializers.BooleanField()


class PlexShareRecipientSerializer(serializers.Serializer):
    """A user a share can go to."""

    id = serializers.IntegerField()
    username = serializers.CharField()


class PlexShareListSerializer(serializers.Serializer):
    """Shares the user granted and received."""

    owned = PlexShareSerializer(many=True)
    received = PlexShareSerializer(many=True)
    recipients = PlexShareRecipientSerializer(many=True)


class PlexShareRequestSerializer(serializers.Serializer):
    """A new share, or the fields of one to change."""

    recipient_id = serializers.IntegerField(required=False, help_text="New shares only.")
    plex_usernames = serializers.ListField(child=serializers.CharField())
    allowed_libraries = serializers.ListField(
        child=serializers.CharField(),
        allow_null=True,
        required=False,
        help_text="Omit or null for every library.",
    )


class PlexShareEnabledSerializer(serializers.Serializer):
    """Accept or pause a received share."""

    enabled = serializers.BooleanField()


def _share_payload(share):
    return {
        "id": share.id,
        "owner": share.owner.username,
        "recipient": share.recipient.username,
        "plex_usernames": _split(share.plex_username),
        "allowed_libraries": share.allowed_libraries,
        "recipient_enabled": share.recipient_enabled,
    }


def _share_error(error):
    status = (
        HTTP.NOT_FOUND
        if isinstance(error, plex_shares.PlexShareNotFoundError)
        else HTTP.BAD_REQUEST
    )
    return Response({"detail": str(error)}, status=status)


def _share_fields(data):
    usernames = data.get("plex_usernames")
    libraries = data.get("allowed_libraries")
    if not _is_text_list(usernames) or (
        libraries is not None and not _is_text_list(libraries)
    ):
        return None, _bad(
            "plex_usernames is a list of strings; allowed_libraries is a list "
            "of strings or null.",
        )
    return (usernames, libraries), None


_SHARES = PlexWebhookShare.objects.select_related("owner", "recipient")


class PlexSharesView(drf_views.APIView):
    """List or create Plex webhook shares."""

    @extend_schema(
        operation_id="listPlexShares",
        responses={200: PlexShareListSerializer},
    )
    def get(self, request):
        """Return shares granted and received, and possible recipients."""
        return Response(
            {
                "owned": [
                    _share_payload(share)
                    for share in _SHARES.filter(owner=request.user).order_by(
                        "recipient__username"
                    )
                ],
                "received": [
                    _share_payload(share)
                    for share in _SHARES.filter(recipient=request.user).order_by(
                        "owner__username"
                    )
                ],
                "recipients": [
                    {"id": user.id, "username": user.username}
                    for user in plex_shares.share_recipients(request.user)
                ],
            },
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="createPlexShare",
        request=PlexShareRequestSerializer,
        responses={
            201: PlexShareSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def post(self, request):
        """Share the Plex webhook; the recipient still has to enable it."""
        data = request.data if isinstance(request.data, dict) else {}
        fields, error = _share_fields(data)
        if error:
            return error
        recipient_id = data.get("recipient_id")
        if isinstance(recipient_id, bool) or not isinstance(recipient_id, int):
            return _bad("recipient_id is required.")
        try:
            share = plex_shares.save_share(
                request.user,
                usernames=fields[0],
                libraries=fields[1],
                recipient_id=recipient_id,
            )
        except plex_shares.PlexShareError as share_error:
            return _share_error(share_error)
        return Response(_share_payload(share), status=HTTP.CREATED)


class PlexShareDetailView(drf_views.APIView):
    """Change or revoke a share the user granted."""

    @extend_schema(
        operation_id="updatePlexShare",
        request=PlexShareRequestSerializer,
        responses={
            200: PlexShareSerializer,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def patch(self, request, share_id):
        """Replace the share's Plex usernames and libraries."""
        data = request.data if isinstance(request.data, dict) else {}
        fields, error = _share_fields(data)
        if error:
            return error
        try:
            share = plex_shares.save_share(
                request.user,
                usernames=fields[0],
                libraries=fields[1],
                share_id=share_id,
            )
        except plex_shares.PlexShareError as share_error:
            return _share_error(share_error)
        return Response(_share_payload(share), status=HTTP.OK)

    @extend_schema(
        operation_id="revokePlexShare",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, share_id):
        """Revoke the share."""
        try:
            plex_shares.delete_share(request.user, share_id)
        except plex_shares.PlexShareError as share_error:
            return _share_error(share_error)
        return Response(status=HTTP.NO_CONTENT)


class PlexShareEnabledView(drf_views.APIView):
    """Accept or pause a share the user received."""

    @extend_schema(
        operation_id="setPlexShareEnabled",
        request=PlexShareEnabledSerializer,
        responses={
            200: PlexShareSerializer,
            400: OpenApiResponse(
                DetailErrorSerializer,
                description="The owner's Plex is not connected.",
            ),
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, share_id):
        """Turn the received share on or off."""
        enabled = (request.data or {}).get("enabled")
        if not isinstance(enabled, bool):
            return _bad("enabled must be a boolean.")
        try:
            share = plex_shares.set_share_enabled(request.user, share_id, enabled=enabled)
        except plex_shares.PlexShareError as share_error:
            return _share_error(share_error)
        return Response(_share_payload(share), status=HTTP.OK)
