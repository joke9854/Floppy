"""Settings > Integrations and RSS for the web (v2 P4-J3).

The screen reads what integrations.html and rss.html render. It includes the
account's legacy key and the webhook URLs built from it, as the Django page
does: the settings screen is `NEVER`-scoped (api/scopes.py), so only the
signed-in browser session can read it, never an API token. The web posts the
pages' own forms with `Accept: application/json` (helpers.answers_json).
"""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from app import helpers


def _when(value):
    return value.isoformat() if value else None


def _cards(request, *, plex_connected, plex_libraries, jellyfin_account) -> list[dict]:
    user = request.user
    import_url = reverse("import_data")
    trakt = getattr(user, "trakt_account", None)
    pocketcasts = getattr(user, "pocketcasts_account", None)

    def card(key, name, method, section, *, connected=False, broken=False, unknown=False, count=0, href=""):
        if broken:
            state = "broken"
        elif connected:
            state = "connected"
        elif unknown:
            state = "unknown"
        else:
            state = "off"
        return {
            "key": key,
            "name": name,
            "method": method,
            "section": section,
            "state": state,
            "count": count if connected else 0,
            "href": href,
            "logo": f"{settings.STATIC_URL}img/{key}-logo.svg",
        }

    return [
        card("plex", "Plex", _("Webhook"), "servers", connected=plex_connected, count=plex_libraries),
        card(
            "jellyfin",
            "Jellyfin",
            _("Official plugin"),
            "servers",
            connected=bool(jellyfin_account and jellyfin_account.is_connected),
            broken=bool(jellyfin_account and jellyfin_account.connection_broken),
        ),
        card("emby", "Emby", _("Webhook"), "servers", unknown=True),
        card("kodi", "Kodi", _("HTTP Scrobbler add-on"), "servers", unknown=True),
        card(
            "trakt",
            "Trakt",
            _("History & ratings"),
            "apps",
            connected=bool(trakt and trakt.is_configured),
            href=f"{import_url}?open=trakt",
        ),
        card("stremio", "Stremio", _("Scrobbler addon"), "apps", unknown=True),
        card("seerr", "Seerr", _("Auto-add requests"), "apps", connected=bool(user.jellyseerr_enabled)),
        card(
            "pocketcasts",
            "Pocket Casts",
            _("Podcasts"),
            "apps",
            connected=bool(pocketcasts and pocketcasts.is_connected),
            broken=bool(pocketcasts and pocketcasts.connection_broken),
            href=f"{import_url}?open=pocketcasts",
        ),
    ]


def _reference_title(reference) -> str:
    title = (reference.metadata or {}).get("title") if isinstance(reference.metadata, dict) else None
    return str(title or reference.external_identity)


def _matches(user) -> dict:
    from integrations.models import ExternalReference, ExternalReferenceReviewStatus

    base = ExternalReference.objects.filter(user=user).select_related("matched_item", "corrected_item")
    review = base.filter(review_status=ExternalReferenceReviewStatus.NEEDS_REVIEW.value).order_by("-updated_at")[:100]
    saved = base.filter(
        review_status__in=(ExternalReferenceReviewStatus.CORRECTED.value, ExternalReferenceReviewStatus.IGNORED.value)
    ).order_by("-updated_at")[:100]
    return {
        "review": [
            {
                "id": reference.pk,
                "title": _reference_title(reference),
                "integration": str(reference.integration),
                "fix_url": reverse("match_fix", args=[reference.matched_item_id]) if reference.matched_item_id else "",
                "ignore_url": reverse("match_reference_status", args=[reference.pk, "ignored"]),
            }
            for reference in review
        ],
        "saved": [
            {
                "id": reference.pk,
                "title": _reference_title(reference),
                "integration": str(reference.integration),
                "status": str(reference.get_review_status_display()),
                "edit_url": reverse("match_fix", args=[reference.corrected_item_id or reference.matched_item_id])
                if (reference.corrected_item_id or reference.matched_item_id)
                else "",
                "remove_url": reverse("match_reference_status", args=[reference.pk, "remove"]),
            }
            for reference in saved
        ],
    }


def _sync(user) -> dict:
    from integrations.state import settings_view

    rows = settings_view.binding_rows(user)
    choices = rows[0]["direction_choices"] if rows else (
        ("off", "Off"),
        ("inbound", "Provider to Floppy"),
        ("outbound", "Floppy to provider"),
        ("both", "Both"),
    )
    bindings = []
    for row in rows:
        binding = row["binding"]
        if row["kill_switch"]:
            badge = _("Paused")
        elif row["is_operational"]:
            badge = _("Active")
        else:
            badge = str(binding.get_status_display())
        capabilities = []
        for capability in row["capability_rows"]:
            if capability["unavailable"]:
                state = "unavailable"
            elif capability["approved"]:
                state = "on"
            elif capability["supported"]:
                state = "off"
            else:
                state = "unsupported"
            capabilities.append({"code": capability["code"], "label": str(capability["label"]), "state": state})
        bindings.append(
            {
                "id": row["id"],
                "label": str(row["label"]),
                "badge": badge,
                "active": bool(row["is_operational"]) and not row["kill_switch"],
                "kill_switch": bool(row["kill_switch"]),
                "direction": row["direction"],
                "last_reconciled_at": _when(row["last_reconciled_at"]),
                "last_error_message": row["last_error_message"] or "",
                "pending_deliveries": row["pending_deliveries"],
                "failed_deliveries": row["failed_deliveries"],
                "open_conflicts": row["open_conflicts"],
                "capabilities": capabilities,
            }
        )
    return {
        "bindings": bindings,
        "conflicts": [
            {
                "id": conflict.pk,
                "item": str(conflict.item),
                "kind": str(conflict.binding.get_client_kind_display()),
                "remote_watched": bool((conflict.remote_snapshot or {}).get("watched")),
                "local_watched": bool((conflict.local_snapshot or {}).get("watched")),
            }
            for conflict in settings_view.open_conflicts(user)
        ],
        "direction_choices": [{"value": value, "label": str(label)} for value, label in choices],
        "urls": {
            "resolve": reverse("sync_resolve_conflict"),
            "pause": reverse("sync_kill_switch"),
            "direction": reverse("sync_direction_settings"),
        },
    }


def _api(user) -> dict:
    from users.views import integration_token_context

    context = integration_token_context(user)
    return {
        # The legacy key, as the Django page shows it (session-only screen).
        "legacy_token": user.token or "",
        "regenerate_url": reverse("regenerate_token"),
        "tokens": [
            {
                "id": token.pk,
                "name": token.name,
                "prefix": token.token_prefix,
                "scopes": list(token.scopes or []),
                "created_at": _when(token.created_at),
                "last_used_at": _when(token.last_used_at),
                "expires_at": _when(token.expires_at),
                "expired": token.is_expired(),
                "revoke_url": reverse("revoke_integration_token", args=[token.pk]),
            }
            for token in context["integration_tokens"]
        ],
        "scope_choices": [
            {"value": choice["value"], "description": str(choice["description"]), "default": choice["default"]}
            for choice in context["integration_scope_choices"]
        ],
        "create_token_url": reverse("create_integration_token"),
        "connected_apps": [
            {
                "client_id": app["client_id"],
                "name": app["name"],
                "scopes": app["scopes"],
                "connected_at": _when(app["connected_at"]),
                "revoke_url": reverse("revoke_connected_app", args=[app["client_id"]]),
            }
            for app in context["connected_apps"]
        ],
    }


def _jellyfin(request, account) -> dict:
    from integrations import tasks
    from integrations.models import ImportRun

    user = request.user
    last_import = (
        ImportRun.objects.filter(user=user, source="jellyfin_playback_reporting").order_by("-started_at").first()
    )
    return {
        "webhook_url": helpers.build_absolute_app_url(request, reverse("jellyfin_webhook", args=[user.token])),
        "mark_played_enabled": bool(user.jellyfin_mark_played_enabled),
        "mark_unplayed_enabled": bool(user.jellyfin_mark_unplayed_enabled),
        "account": None
        if account is None
        else {
            "connected": bool(account.is_connected),
            "base_url": account.base_url,
            "username": account.jellyfin_username or "",
            "last_sync_at": _when(account.last_sync_at),
            "last_error_message": account.last_error_message or "",
            "playback_reporting_available": account.playback_reporting_available,
            "last_pull_at": _when(account.last_pull_at),
            "last_pull_error_message": account.last_pull_error_message or "",
            "pull_history_enabled": bool(account.pull_history_enabled),
            "push_watched_enabled": bool(account.push_watched_enabled),
            "push_unwatched_enabled": bool(account.push_unwatched_enabled),
            "scheduled_push_enabled": bool(account.scheduled_push_enabled),
            "instant_push_enabled": bool(account.instant_push_enabled),
        },
        "last_import": None
        if last_import is None
        else {
            "status": str(last_import.get_status_display()),
            "started_at": _when(last_import.started_at),
            "created": last_import.created_count or 0,
            "skipped": last_import.skipped_count or 0,
        },
        "pull_interval_minutes": tasks.JELLYFIN_PULL_INTERVAL_MINUTES,
        "urls": {
            "events": reverse("update_jellyfin_webhook_events"),
            "connect": reverse("jellyfin_connect"),
            "disconnect": reverse("jellyfin_disconnect"),
            "settings": reverse("jellyfin_settings"),
            "push": reverse("jellyfin_push_now"),
            "pull": reverse("jellyfin_pull_now"),
            "upload": reverse("jellyfin_playback_reporting_import"),
        },
    }


def _plex(request, plex_account) -> dict:
    from django.contrib.auth import get_user_model

    from integrations import tasks
    from integrations.models import PlexWebhookShare
    from users import views as user_views

    user = request.user
    connected = bool(plex_account and plex_account.plex_token)
    options = []
    if connected:
        if user_views._should_refresh_plex_sections(plex_account):
            tasks.refresh_plex_sections.delay(user.id)
        for section in plex_account.sections or []:
            machine, section_id = section.get("machine_identifier"), section.get("id")
            if not machine or not section_id:
                continue
            options.append(
                {
                    "value": f"{machine}::{section_id}",
                    "label": section.get("title") or f"Library {section_id}",
                    "server_name": section.get("server_name") or "",
                }
            )
    all_values = [option["value"] for option in options]
    rotated, received = user.plex_webhook_token_rotated_at, user.plex_webhook_last_received_at
    if rotated and (not received or received < rotated):
        status = "needs_update"
    elif user.plex_webhook_last_error:
        status = "error"
    elif received:
        status = "received"
    else:
        status = "none"
    owned = PlexWebhookShare.objects.filter(owner=user).select_related("recipient").order_by("recipient__username")
    incoming = PlexWebhookShare.objects.filter(recipient=user).select_related("owner").order_by("owner__username")
    recipients = (
        get_user_model()
        .objects.filter(is_active=True, is_demo=False, is_test_account=False)
        .exclude(pk=user.pk)
        .order_by("username")
    )
    return {
        "connected": connected,
        "usernames": user.plex_usernames or "",
        "libraries": options,
        "selected_libraries": list(user.plex_webhook_libraries or all_values) if connected else [],
        "shares": [
            {
                "id": share.pk,
                "recipient": share.recipient.username,
                "plex_username": share.plex_username,
                "libraries": share.allowed_libraries if share.allowed_libraries is not None else all_values,
                "all_libraries": share.allowed_libraries is None,
                "recipient_enabled": bool(share.recipient_enabled),
            }
            for share in owned
        ],
        "received": [
            {
                "id": share.pk,
                "owner": share.owner.username,
                "plex_username": share.plex_username,
                "libraries": "all"
                if share.allowed_libraries is None
                else ("selected" if share.allowed_libraries else "none"),
                "enabled": bool(share.recipient_enabled),
            }
            for share in incoming
        ],
        "recipients": [{"id": recipient.pk, "username": recipient.username} for recipient in recipients],
        "webhook": {
            "status": status,
            "rotated_at": _when(rotated),
            "error": user.plex_webhook_last_error or "",
            "error_at": _when(user.plex_webhook_last_error_at),
            "last_received_at": _when(received),
        },
        "webhook_url": helpers.build_absolute_app_url(request, reverse("plex_webhook", args=[user.token])),
        "urls": {
            "usernames": reverse("update_plex_usernames"),
            "libraries": reverse("update_plex_webhook_libraries"),
            "share": reverse("update_plex_webhook_share"),
            "delete_share": reverse("delete_plex_webhook_share"),
            "toggle_share": reverse("toggle_plex_webhook_share"),
        },
    }


def _stremio(request) -> dict:
    from integrations import stremio_catalog
    from integrations.models import CatalogGrant

    user = request.user
    grants = list(CatalogGrant.objects.filter(user=user, revoked_at__isnull=True).order_by("-created_at"))
    # As on the Django page: the newest install credential, else the account key.
    credential = grants[0].token if grants else user.token
    return {
        "addon_url": helpers.build_absolute_app_url(request, reverse("stremio_addon_manifest", args=[credential])),
        "configure_url": reverse("stremio_addon_configure", args=[user.token]),
        "import_url": reverse("import_data"),
        "grants": [
            {
                "id": grant.pk,
                "name": grant.name,
                "created_at": _when(grant.created_at),
                "last_used_at": _when(getattr(grant, "last_used_at", None)),
                "allow_playback_start": bool(grant.allow_playback_start),
                "revoke_url": reverse("revoke_catalog_grant", args=[grant.pk]),
            }
            for grant in grants
        ],
        "create_grant_url": reverse("create_catalog_grant"),
        "readiness": [
            {
                "noun": str(entry["noun"]),
                "list_name": str(entry["list_name"]),
                "total": entry["total"],
                "publishable": entry["publishable"],
                "unresolved": entry["unresolved"],
            }
            for entry in stremio_catalog.catalog_readiness(user)
        ],
    }


def _seerr(request) -> dict:
    user = request.user
    return {
        "enabled": bool(user.jellyseerr_enabled),
        "trigger_statuses": user.jellyseerr_trigger_statuses or "",
        "allowed_usernames": user.jellyseerr_allowed_usernames or "",
        "default_added_status": user.jellyseerr_default_added_status or "Planning",
        "default_status_choices": ["Planning", "In progress"],
        "save_url": reverse("update_jellyseerr_settings"),
        "webhook_url": helpers.build_absolute_app_url(request, reverse("jellyseerr_webhook", args=[user.token])),
        "global_enabled": bool(settings.SEERR_GLOBAL_WEBHOOK_SECRET),
        "global_webhook_url": helpers.build_absolute_app_url(request, reverse("seerr_global_webhook"))
        if settings.SEERR_GLOBAL_WEBHOOK_SECRET
        else "",
    }


def build_integrations(request) -> dict:
    """Integrations: the card grid and each integration's panel."""
    user = request.user
    plex_account = getattr(user, "plex_account", None)
    jellyfin_account = getattr(user, "jellyfin_account", None)
    plex = _plex(request, plex_account)
    return {
        "is_demo": user.is_demo,
        "cards": _cards(
            request,
            plex_connected=plex["connected"],
            plex_libraries=len(plex["libraries"]),
            jellyfin_account=jellyfin_account,
        ),
        "matches": _matches(user),
        "sync": _sync(user),
        "api": _api(user),
        "jellyfin": _jellyfin(request, jellyfin_account),
        "plex": plex,
        "emby_webhook_url": helpers.build_absolute_app_url(request, reverse("emby_webhook", args=[user.token])),
        "kodi_webhook_url": helpers.build_absolute_app_url(request, reverse("kodi_webhook", args=[user.token])),
        "stremio": _stremio(request),
        "seerr": _seerr(request),
        "nuvio_server_url": helpers.build_absolute_app_url(request, "/"),
        "onboarding_url": reverse("onboarding_integration_setup"),
    }


def build_rss(request) -> dict:
    """RSS: Discover rows backed by external metadata, as feeds."""
    from app.discover.feeds import get_external_row_definitions
    from app.discover.registry import DISCOVER_MEDIA_TYPES
    from app.models import MediaTypes

    placeholder_type, placeholder_row = DISCOVER_MEDIA_TYPES[0], "trending_right_now"
    template = request.build_absolute_uri(
        reverse(
            "discover_row_feed",
            kwargs={"token": request.user.token, "media_type": placeholder_type, "row_key": placeholder_row},
        )
    )
    template = template.replace(f"/{placeholder_type}/", "/MEDIA_TYPE_PLACEHOLDER/").replace(
        f"{placeholder_row}.xml", "ROW_KEY_PLACEHOLDER.xml"
    )
    return {
        "media_types": [
            {
                "value": media_type,
                "label": str(MediaTypes(media_type).label),
                "rows": [{"key": row.key, "title": str(row.title)} for row in get_external_row_definitions(media_type)],
            }
            for media_type in DISCOVER_MEDIA_TYPES
        ],
        "feed_url_template": template,
        "preview_url": reverse("discover_row_feed_preview"),
        "integrations_url": reverse("integrations"),
    }


# Serializers (the OpenAPI contract for the web types).


class IntegrationsCardSerializer(serializers.Serializer):
    """A card on the grid (`state`: connected, broken, unknown, off; `href`: opens elsewhere)."""

    key = serializers.CharField()
    name = serializers.CharField()
    method = serializers.CharField()
    section = serializers.ChoiceField(choices=["servers", "apps"])
    state = serializers.ChoiceField(choices=["connected", "broken", "unknown", "off"])
    count = serializers.IntegerField()
    href = serializers.CharField(allow_blank=True)
    logo = serializers.CharField()


class IntegrationsReviewSerializer(serializers.Serializer):
    """A provider identity that was not safe to match automatically."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    integration = serializers.CharField()
    fix_url = serializers.CharField(allow_blank=True)
    ignore_url = serializers.CharField()


class IntegrationsSavedMatchSerializer(serializers.Serializer):
    """A saved match decision."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    integration = serializers.CharField()
    status = serializers.CharField()
    edit_url = serializers.CharField(allow_blank=True)
    remove_url = serializers.CharField()


class IntegrationsMatchesSerializer(serializers.Serializer):
    """Matching review and saved decisions (100 each at most)."""

    review = IntegrationsReviewSerializer(many=True)
    saved = IntegrationsSavedMatchSerializer(many=True)


class IntegrationsCapabilitySerializer(serializers.Serializer):
    """A sync capability (`state`: on, off, unavailable, unsupported)."""

    code = serializers.CharField()
    label = serializers.CharField()
    state = serializers.ChoiceField(choices=["on", "off", "unavailable", "unsupported"])


class IntegrationsBindingSerializer(serializers.Serializer):
    """A watched-state sync connection."""

    id = serializers.IntegerField()
    label = serializers.CharField()
    badge = serializers.CharField()
    active = serializers.BooleanField()
    kill_switch = serializers.BooleanField()
    direction = serializers.CharField()
    last_reconciled_at = serializers.DateTimeField(allow_null=True)
    last_error_message = serializers.CharField(allow_blank=True)
    pending_deliveries = serializers.IntegerField()
    failed_deliveries = serializers.IntegerField()
    open_conflicts = serializers.IntegerField()
    capabilities = IntegrationsCapabilitySerializer(many=True)


class IntegrationsConflictSerializer(serializers.Serializer):
    """An item both sides changed."""

    id = serializers.IntegerField()
    item = serializers.CharField()
    kind = serializers.CharField()
    remote_watched = serializers.BooleanField()
    local_watched = serializers.BooleanField()


class IntegrationsChoiceSerializer(serializers.Serializer):
    """A value and its label."""

    value = serializers.CharField()
    label = serializers.CharField()


class IntegrationsSyncUrlsSerializer(serializers.Serializer):
    """Where the sync forms post."""

    resolve = serializers.CharField()
    pause = serializers.CharField()
    direction = serializers.CharField()


class IntegrationsSyncSerializer(serializers.Serializer):
    """Watched-state sync."""

    bindings = IntegrationsBindingSerializer(many=True)
    conflicts = IntegrationsConflictSerializer(many=True)
    direction_choices = IntegrationsChoiceSerializer(many=True)
    urls = IntegrationsSyncUrlsSerializer()


class IntegrationsTokenSerializer(serializers.Serializer):
    """A named app token (the secret is shown once, by the create answer)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    prefix = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    created_at = serializers.DateTimeField(allow_null=True)
    last_used_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    expired = serializers.BooleanField()
    revoke_url = serializers.CharField()


class IntegrationsScopeSerializer(serializers.Serializer):
    """A permission a token can have (`default`: in the tracking preset)."""

    value = serializers.CharField()
    description = serializers.CharField()
    default = serializers.BooleanField()


class IntegrationsConnectedAppSerializer(serializers.Serializer):
    """An app signed in with the Floppy account."""

    client_id = serializers.CharField()
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    connected_at = serializers.DateTimeField(allow_null=True)
    revoke_url = serializers.CharField()


class IntegrationsApiSerializer(serializers.Serializer):
    """The legacy key, app tokens and connected apps."""

    legacy_token = serializers.CharField(allow_blank=True)
    regenerate_url = serializers.CharField()
    tokens = IntegrationsTokenSerializer(many=True)
    scope_choices = IntegrationsScopeSerializer(many=True)
    create_token_url = serializers.CharField()
    connected_apps = IntegrationsConnectedAppSerializer(many=True)


class IntegrationsJellyfinAccountSerializer(serializers.Serializer):
    """The Floppy → Jellyfin connection."""

    connected = serializers.BooleanField()
    base_url = serializers.CharField()
    username = serializers.CharField(allow_blank=True)
    last_sync_at = serializers.DateTimeField(allow_null=True)
    last_error_message = serializers.CharField(allow_blank=True)
    playback_reporting_available = serializers.BooleanField(allow_null=True)
    last_pull_at = serializers.DateTimeField(allow_null=True)
    last_pull_error_message = serializers.CharField(allow_blank=True)
    pull_history_enabled = serializers.BooleanField()
    push_watched_enabled = serializers.BooleanField()
    push_unwatched_enabled = serializers.BooleanField()
    scheduled_push_enabled = serializers.BooleanField()
    instant_push_enabled = serializers.BooleanField()


class IntegrationsImportRunSerializer(serializers.Serializer):
    """The last Playback Reporting upload."""

    status = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    created = serializers.IntegerField()
    skipped = serializers.IntegerField()


class IntegrationsJellyfinUrlsSerializer(serializers.Serializer):
    """Where the Jellyfin forms post."""

    events = serializers.CharField()
    connect = serializers.CharField()
    disconnect = serializers.CharField()
    settings = serializers.CharField()
    push = serializers.CharField()
    pull = serializers.CharField()
    upload = serializers.CharField()


class IntegrationsJellyfinSerializer(serializers.Serializer):
    """Jellyfin webhooks and the Floppy → Jellyfin connection."""

    webhook_url = serializers.CharField()
    mark_played_enabled = serializers.BooleanField()
    mark_unplayed_enabled = serializers.BooleanField()
    account = IntegrationsJellyfinAccountSerializer(allow_null=True)
    last_import = IntegrationsImportRunSerializer(allow_null=True)
    pull_interval_minutes = serializers.IntegerField()
    urls = IntegrationsJellyfinUrlsSerializer()


class IntegrationsPlexLibrarySerializer(serializers.Serializer):
    """A Plex library (`value`: machine::section)."""

    value = serializers.CharField()
    label = serializers.CharField()
    server_name = serializers.CharField(allow_blank=True)


class IntegrationsPlexShareSerializer(serializers.Serializer):
    """A share of this account's Plex webhook."""

    id = serializers.IntegerField()
    recipient = serializers.CharField()
    plex_username = serializers.CharField()
    libraries = serializers.ListField(child=serializers.CharField())
    all_libraries = serializers.BooleanField()
    recipient_enabled = serializers.BooleanField()


class IntegrationsPlexReceivedSerializer(serializers.Serializer):
    """A Plex webhook another user shared (`libraries`: all, selected, none)."""

    id = serializers.IntegerField()
    owner = serializers.CharField()
    plex_username = serializers.CharField()
    libraries = serializers.ChoiceField(choices=["all", "selected", "none"])
    enabled = serializers.BooleanField()


class IntegrationsRecipientSerializer(serializers.Serializer):
    """A user a webhook can be shared with."""

    id = serializers.IntegerField()
    username = serializers.CharField()


class IntegrationsPlexWebhookSerializer(serializers.Serializer):
    """The Plex webhook's status (needs_update, error, received, none)."""

    status = serializers.ChoiceField(choices=["needs_update", "error", "received", "none"])
    rotated_at = serializers.DateTimeField(allow_null=True)
    error = serializers.CharField(allow_blank=True)
    error_at = serializers.DateTimeField(allow_null=True)
    last_received_at = serializers.DateTimeField(allow_null=True)


class IntegrationsPlexUrlsSerializer(serializers.Serializer):
    """Where the Plex forms post."""

    usernames = serializers.CharField()
    libraries = serializers.CharField()
    share = serializers.CharField()
    delete_share = serializers.CharField()
    toggle_share = serializers.CharField()


class IntegrationsPlexSerializer(serializers.Serializer):
    """Plex webhook filters, shares and status."""

    connected = serializers.BooleanField()
    usernames = serializers.CharField(allow_blank=True)
    libraries = IntegrationsPlexLibrarySerializer(many=True)
    selected_libraries = serializers.ListField(child=serializers.CharField())
    shares = IntegrationsPlexShareSerializer(many=True)
    received = IntegrationsPlexReceivedSerializer(many=True)
    recipients = IntegrationsRecipientSerializer(many=True)
    webhook = IntegrationsPlexWebhookSerializer()
    webhook_url = serializers.CharField()
    urls = IntegrationsPlexUrlsSerializer()


class IntegrationsGrantSerializer(serializers.Serializer):
    """A Stremio install credential (its token is never returned here)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    created_at = serializers.DateTimeField(allow_null=True)
    last_used_at = serializers.DateTimeField(allow_null=True)
    allow_playback_start = serializers.BooleanField()
    revoke_url = serializers.CharField()


class IntegrationsReadinessSerializer(serializers.Serializer):
    """How many titles of a list Stremio can show."""

    noun = serializers.CharField()
    list_name = serializers.CharField()
    total = serializers.IntegerField()
    publishable = serializers.IntegerField()
    unresolved = serializers.IntegerField()


class IntegrationsStremioSerializer(serializers.Serializer):
    """Stremio: the addon URL (newest install credential, else the account key)."""

    addon_url = serializers.CharField()
    configure_url = serializers.CharField()
    import_url = serializers.CharField()
    grants = IntegrationsGrantSerializer(many=True)
    create_grant_url = serializers.CharField()
    readiness = IntegrationsReadinessSerializer(many=True)


class IntegrationsSeerrSerializer(serializers.Serializer):
    """Seerr: the settings form and webhook URLs."""

    enabled = serializers.BooleanField()
    trigger_statuses = serializers.CharField(allow_blank=True)
    allowed_usernames = serializers.CharField(allow_blank=True)
    default_added_status = serializers.CharField()
    default_status_choices = serializers.ListField(child=serializers.CharField())
    save_url = serializers.CharField()
    webhook_url = serializers.CharField()
    global_enabled = serializers.BooleanField()
    global_webhook_url = serializers.CharField(allow_blank=True)


class SettingsIntegrationsSerializer(serializers.Serializer):
    """Integrations (session only: carries the legacy key and URLs built on it)."""

    is_demo = serializers.BooleanField()
    cards = IntegrationsCardSerializer(many=True)
    matches = IntegrationsMatchesSerializer()
    sync = IntegrationsSyncSerializer()
    api = IntegrationsApiSerializer()
    jellyfin = IntegrationsJellyfinSerializer()
    plex = IntegrationsPlexSerializer()
    emby_webhook_url = serializers.CharField()
    kodi_webhook_url = serializers.CharField()
    stremio = IntegrationsStremioSerializer()
    seerr = IntegrationsSeerrSerializer()
    nuvio_server_url = serializers.CharField()
    onboarding_url = serializers.CharField()


class RssRowSerializer(serializers.Serializer):
    """A Discover row that can be a feed."""

    key = serializers.CharField()
    title = serializers.CharField()


class RssMediaTypeSerializer(serializers.Serializer):
    """A media type and its feed rows."""

    value = serializers.CharField()
    label = serializers.CharField()
    rows = RssRowSerializer(many=True)


class SettingsRssSerializer(serializers.Serializer):
    """RSS: fill MEDIA_TYPE_PLACEHOLDER and ROW_KEY_PLACEHOLDER in the template."""

    media_types = RssMediaTypeSerializer(many=True)
    feed_url_template = serializers.CharField()
    preview_url = serializers.CharField()
    integrations_url = serializers.CharField()
