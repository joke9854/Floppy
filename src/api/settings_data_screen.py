"""Settings > Metadata, Export, Advanced and Connected apps for the web (v2 P4-J2).

Each builder reads what the Django page renders. The web posts the pages'
own forms with `Accept: application/json` (helpers.answers_json). Credential
values never leave the server: a field carries only the masked preview the
Django page already shows, and the TMDB proxy only whether one is set.
"""

from __future__ import annotations

from django.conf import settings
from django.db.models import Max
from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

from app import image_cache
from app.models import MediaTypes
from app.templatetags import app_tags


def _label(media_type: str) -> str:
    return str(app_tags.media_type_readable_plural(media_type))


def build_metadata(request) -> dict:
    """Metadata: the provider per library and the provider credentials."""
    from django.contrib.auth import get_user_model

    from app import preflight
    from app.providers import credentials
    from users import metadata_views
    from users.models import AnimeLibraryModeChoices

    user = request.user
    can_edit_instance = user.is_superuser
    groups = []
    for group in credentials.GROUP_ORDER:
        specs = [spec for spec in credentials.REGISTRY.values() if spec.group == group]
        providers = sorted(
            (metadata_views._provider_view(spec, user) for spec in specs),
            key=lambda provider: provider["label"].casefold(),
        )
        if not providers:
            continue
        for provider in providers:
            slug = provider["slug"]
            provider["urls"] = {
                "save": reverse("save_provider_credential", args=[slug]),
                "clear": reverse("clear_provider_credential", args=[slug]),
                "personal": reverse("save_personal_credential", args=[slug]),
            }
            provider["settable_media_types"] = [
                {
                    "value": media_type,
                    "label": _label(media_type),
                    "url": reverse("set_media_type_provider", args=[media_type]),
                }
                for media_type in provider["settable_media_types"]
            ]
            provider.pop("personal_fields", None)
        groups.append(
            {
                "key": group,
                "label": str(credentials.GROUP_LABELS[group]),
                "description": str(credentials.GROUP_DESCRIPTIONS[group]),
                "providers": providers,
            }
        )
    libraries = []
    for entry in metadata_views._provider_summary(user):
        media_type = entry["media_type"]
        libraries.append(
            {
                "media_type": media_type,
                "label": _label(media_type),
                "current_provider": entry["current_provider"] or "",
                "current_label": str(entry["current_label"]),
                # Only a configured source passes the view's check.
                "choices": [
                    {"value": choice["value"], "label": str(choice["label"]), "configured": choice["configured"]}
                    for choice in entry["choices"]
                ],
                "configurable": entry["configurable"],
                "url": reverse("set_media_type_provider", args=[media_type])
                if entry["configurable"]
                else "",
            }
        )
    promote = None
    if not can_edit_instance:
        promote = {
            "instance_has_superuser": get_user_model().objects.filter(is_superuser=True).exists(),
            "in_container": preflight.in_container(),
            "command": metadata_views._promote_command(user.username),
        }
    return {
        "is_demo": user.is_demo,
        "can_edit_instance": can_edit_instance,
        "promote": promote,
        "libraries": libraries,
        "groups": groups,
        "anime_library_mode": user.anime_library_mode,
        "anime_library_modes": [
            {"value": value, "label": str(label)} for value, label in AnimeLibraryModeChoices.choices
        ],
        "convert_anime_url": reverse("convert_anime_library"),
    }


def _when(value):
    return value.isoformat() if value else None


def build_export(request) -> dict:
    """Export: the CSV form, where scheduled exports land, schedules, history."""
    from users import views as user_views

    user = request.user
    tasks = user.get_export_tasks()
    media_types = [
        media_type.value
        for media_type in MediaTypes
        if media_type.value not in (MediaTypes.EPISODE.value, MediaTypes.SEASON.value)
    ]
    return {
        "is_demo": user.is_demo,
        "media_types": [{"value": value, "label": _label(value)} for value in media_types],
        "backup": user_views._backup_dir_status(user),
        "snapshot": user_views._db_snapshot_status(),
        "schedules": [
            {
                "task_name": schedule["task"].name,
                "schedule": str(schedule["schedule"]),
                "media_types": schedule["media_types"],
                "include_lists": bool(schedule["include_lists"]),
                "include_collection": bool(schedule["include_collection"]),
                "last_run": _when(schedule["last_run"]),
                "next_run": _when(schedule["next_run"]),
            }
            for schedule in tasks["schedules"]
        ],
        "results": [
            {
                "date": _when(result["date"]),
                "status": result["status"] or "",
                "summary": str(result["summary"] or ""),
                "errors": str(result["errors"] or ""),
            }
            for result in tasks["results"]
        ],
        "urls": {
            "export": reverse("create_export_schedule"),
            "delete_schedule": reverse("delete_export_schedule"),
            "letterboxd": reverse("export_csv_letterboxd"),
        },
    }


def build_advanced(request) -> dict:
    """Advanced: logs, image caching, caches, the danger zone, TMDB proxy."""
    from urllib.parse import urlencode

    from users import views as user_views

    user = request.user
    stats = image_cache.cache_stats()
    bug_body = (
        f"**Floppy version:** {settings.VERSION}\n\n"
        "**Describe the issue:**\n\n\n"
        "**Steps to reproduce:**\n\n\n"
        "**Logs:** attach the file downloaded from Settings > Advanced > "
        "Download Sanitized Logs"
    )
    caches = [
        ("search", _("Search Cache"), _("Provider search results — shared instance-wide"), "clear_search_cache"),
        ("history", _("History Cache"), _("Your cached History page — just you"), "clear_history_cache"),
        ("statistics", _("Statistics Cache"), _("Your cached Statistics page — just you"), "clear_statistics_cache"),
        (
            "discover",
            _("Discover Cache"),
            _("Your recommendation rows & taste profile — just you"),
            "clear_discover_cache",
        ),
    ]
    return {
        "is_demo": user.is_demo,
        "is_superuser": user.is_superuser,
        "bug_report_url": "https://github.com/dannyvfilms/Floppy/issues/new?"
        + urlencode({"title": "[BUG] ", "body": bug_body}),
        "image_cache": {
            "enabled": image_cache.is_enabled(),
            "days": image_cache.retention_days(),
            "day_choices": [7, 15, 30],
            "count": stats["count"],
            "size": image_cache.format_bytes(stats["bytes"]),
        },
        "caches": [
            {"key": key, "label": str(label), "note": str(note), "url": reverse(name)}
            for key, label, note, name in caches
        ],
        "media_types": [{"value": value, "label": _label(value)} for value in user_views.DELETABLE_MEDIA_TYPES],
        "tmdb_proxy_configured": bool(user.tmdb_proxy_url),
        "urls": {
            "logs": reverse("export_logs"),
            "image_cache": reverse("update_image_cache"),
            "clear_image_cache": reverse("clear_image_cache"),
            "clear_all": reverse("clear_all_caches"),
            "delete_media_type": reverse("bulk_delete_by_media_type"),
            "tmdb_proxy": reverse("update_tmdb_proxy"),
        },
    }


def build_connected_apps(request) -> dict:
    """Return Connected apps: signed-in installs, sync connections, crash reports."""
    from integrations.models import SyncBinding, SyncClientKind
    from users import views as user_views

    user = request.user
    reports = user.cinetrack_crash_reports.order_by("-received_at", "-pk")
    connections = (
        SyncBinding.objects.filter(user=user, client_kind=SyncClientKind.APP.value)
        .annotate(last_sync=Max("checkpoints__updated_at"))
        .order_by("-last_sync", "label")
    )
    return {
        "sessions": [
            {
                "id": session["id"],
                "name": session["name"],
                "scopes": session["scopes"],
                "last_active": _when(session["last_active"]),
                "revoke_url": reverse("revoke_app_session", args=[session["id"]]),
            }
            for session in user_views.app_sessions_for(user)
        ],
        "sync_connections": [
            {
                "label": connection.label or str(connection.get_client_kind_display()),
                "status": str(connection.get_status_display()),
                "last_sync": _when(connection.last_sync),
            }
            for connection in connections
        ],
        "crash_reports": [
            {
                "id": report.pk,
                "kind": str(report.get_kind_display()),
                "exception_class": report.exception_class or "",
                "occurred_at": _when(report.occurred_at),
                "app_version": report.app_version or "",
                "device_model": report.device_model or "",
                "android_sdk": report.android_sdk,
                "stack_trace": report.stack_trace or "",
            }
            for report in reports[: user_views.CONNECTED_APPS_CRASH_REPORT_LIMIT]
        ],
        "crash_report_count": reports.count(),
        "urls": {
            "export_crash_reports": reverse("export_crash_reports"),
            "integrations": reverse("integrations"),
        },
    }


# Serializers (the OpenAPI contract for the web types).


class SettingsCredentialFieldSerializer(serializers.Serializer):
    """A credential field. `preview` is masked (last 4 characters at most)."""

    name = serializers.CharField()
    label = serializers.CharField()
    secret = serializers.BooleanField()
    required = serializers.BooleanField()
    placeholder = serializers.CharField(allow_blank=True)
    setting = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True, allow_null=True)
    locked = serializers.BooleanField()
    preview = serializers.CharField(allow_blank=True)
    has_instance_value = serializers.BooleanField()
    personal = serializers.BooleanField()
    has_personal_value = serializers.BooleanField()


class SettingsProviderUrlsSerializer(serializers.Serializer):
    """Where a provider's forms post."""

    save = serializers.CharField()
    clear = serializers.CharField()
    personal = serializers.CharField()


class SettingsSettableTypeSerializer(serializers.Serializer):
    """A library this provider can be the default for."""

    value = serializers.CharField()
    label = serializers.CharField()
    url = serializers.CharField()


class SettingsProviderSerializer(serializers.Serializer):
    """A metadata provider and its credentials."""

    slug = serializers.CharField()
    label = serializers.CharField()
    logo_slug = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    docs_url = serializers.CharField(allow_blank=True, allow_null=True)
    user_scope = serializers.BooleanField()
    configured = serializers.BooleanField()
    status = serializers.CharField(allow_blank=True)
    fields = SettingsCredentialFieldSerializer(many=True)
    locked = serializers.BooleanField()
    has_instance_value = serializers.BooleanField()
    settable_media_types = SettingsSettableTypeSerializer(many=True)
    urls = SettingsProviderUrlsSerializer()


class SettingsProviderGroupSerializer(serializers.Serializer):
    """Providers grouped by what they supply."""

    key = serializers.CharField()
    label = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    providers = SettingsProviderSerializer(many=True)


class SettingsProviderChoiceSerializer(serializers.Serializer):
    """A source a library can use; only a configured one can be saved."""

    value = serializers.CharField()
    label = serializers.CharField()
    configured = serializers.BooleanField()


class SettingsLibraryProviderSerializer(serializers.Serializer):
    """The provider one library uses (`configurable`: it can be changed)."""

    media_type = serializers.CharField()
    label = serializers.CharField()
    current_provider = serializers.CharField(allow_blank=True)
    current_label = serializers.CharField()
    choices = SettingsProviderChoiceSerializer(many=True)
    configurable = serializers.BooleanField()
    url = serializers.CharField(allow_blank=True)


class SettingsPromoteSerializer(serializers.Serializer):
    """How a non-superuser becomes one."""

    instance_has_superuser = serializers.BooleanField()
    in_container = serializers.BooleanField()
    command = serializers.CharField()


class SettingsValueLabelSerializer(serializers.Serializer):
    """A value and its label."""

    value = serializers.CharField()
    label = serializers.CharField()


class SettingsMetadataSerializer(serializers.Serializer):
    """Metadata providers and credentials."""

    is_demo = serializers.BooleanField()
    can_edit_instance = serializers.BooleanField()
    promote = SettingsPromoteSerializer(allow_null=True)
    libraries = SettingsLibraryProviderSerializer(many=True)
    groups = SettingsProviderGroupSerializer(many=True)
    anime_library_mode = serializers.CharField()
    anime_library_modes = SettingsValueLabelSerializer(many=True)
    convert_anime_url = serializers.CharField()


class SettingsBackupStatusSerializer(serializers.Serializer):
    """A backup directory, how many files it holds, and whether the host sees it."""

    path = serializers.CharField()
    file_count = serializers.IntegerField()
    host_reachable = serializers.BooleanField()


class SettingsSnapshotStatusSerializer(SettingsBackupStatusSerializer):
    """The database snapshot directory (`enabled`: DB_SNAPSHOT_ENABLED)."""

    enabled = serializers.BooleanField()


class SettingsExportScheduleSerializer(serializers.Serializer):
    """A recurring export (`media_types` null: all of them)."""

    task_name = serializers.CharField()
    schedule = serializers.CharField()
    media_types = serializers.ListField(child=serializers.CharField(), allow_null=True)
    include_lists = serializers.BooleanField()
    include_collection = serializers.BooleanField()
    last_run = serializers.DateTimeField(allow_null=True)
    next_run = serializers.DateTimeField(allow_null=True)


class SettingsExportResultSerializer(serializers.Serializer):
    """A scheduled export run from the last 7 days."""

    date = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    errors = serializers.CharField(allow_blank=True)


class SettingsExportUrlsSerializer(serializers.Serializer):
    """Where the export forms post."""

    export = serializers.CharField()
    delete_schedule = serializers.CharField()
    letterboxd = serializers.CharField()


class SettingsExportSerializer(serializers.Serializer):
    """Export: the CSV form posts to `urls.export` and answers with the file."""

    is_demo = serializers.BooleanField()
    media_types = SettingsValueLabelSerializer(many=True)
    backup = SettingsBackupStatusSerializer()
    snapshot = SettingsSnapshotStatusSerializer()
    schedules = SettingsExportScheduleSerializer(many=True)
    results = SettingsExportResultSerializer(many=True)
    urls = SettingsExportUrlsSerializer()


class SettingsImageCacheSerializer(serializers.Serializer):
    """Instance-wide image caching (superusers change it)."""

    enabled = serializers.BooleanField()
    days = serializers.IntegerField()
    day_choices = serializers.ListField(child=serializers.IntegerField())
    count = serializers.IntegerField()
    size = serializers.CharField()


class SettingsCacheSerializer(serializers.Serializer):
    """A cache the user can clear."""

    key = serializers.CharField()
    label = serializers.CharField()
    note = serializers.CharField()
    url = serializers.CharField()


class SettingsAdvancedUrlsSerializer(serializers.Serializer):
    """Where the Advanced forms post."""

    logs = serializers.CharField()
    image_cache = serializers.CharField()
    clear_image_cache = serializers.CharField()
    clear_all = serializers.CharField()
    delete_media_type = serializers.CharField()
    tmdb_proxy = serializers.CharField()


class SettingsAdvancedSerializer(serializers.Serializer):
    """Advanced. The TMDB proxy URL is never returned, only whether one is set."""

    is_demo = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    bug_report_url = serializers.CharField()
    image_cache = SettingsImageCacheSerializer()
    caches = SettingsCacheSerializer(many=True)
    media_types = SettingsValueLabelSerializer(many=True)
    tmdb_proxy_configured = serializers.BooleanField()
    urls = SettingsAdvancedUrlsSerializer()


class SettingsAppSessionSerializer(serializers.Serializer):
    """A signed-in install."""

    id = serializers.CharField()
    name = serializers.CharField()
    scopes = serializers.ListField(child=serializers.CharField())
    last_active = serializers.DateTimeField(allow_null=True)
    revoke_url = serializers.CharField()


class SettingsSyncConnectionSerializer(serializers.Serializer):
    """An app that syncs the library."""

    label = serializers.CharField()
    status = serializers.CharField()
    last_sync = serializers.DateTimeField(allow_null=True)


class SettingsCrashReportSerializer(serializers.Serializer):
    """A CineTrack crash report."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    exception_class = serializers.CharField(allow_blank=True)
    occurred_at = serializers.DateTimeField(allow_null=True)
    app_version = serializers.CharField(allow_blank=True)
    device_model = serializers.CharField(allow_blank=True)
    android_sdk = serializers.IntegerField(allow_null=True)
    stack_trace = serializers.CharField(allow_blank=True)


class SettingsConnectedAppsUrlsSerializer(serializers.Serializer):
    """Connected apps links."""

    export_crash_reports = serializers.CharField()
    integrations = serializers.CharField()


class SettingsConnectedAppsSerializer(serializers.Serializer):
    """Connected apps (the newest 50 crash reports; the export has all)."""

    sessions = SettingsAppSessionSerializer(many=True)
    sync_connections = SettingsSyncConnectionSerializer(many=True)
    crash_reports = SettingsCrashReportSerializer(many=True)
    crash_report_count = serializers.IntegerField()
    urls = SettingsConnectedAppsUrlsSerializer()
