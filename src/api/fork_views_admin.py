"""Instance administration and account maintenance through the API (P1-I).

Provider credentials and defaults, image cache, server port, TMDB proxy,
cache clearing, bulk delete and log download. Everything here is scoped
`NEVER`: no token may reach it, only a signed-in browser session (P3's
session bridge), like credential management. Instance-wide changes also
need a superuser (403 otherwise).

Credential values are never returned, only a masked preview the web page
already shows. Bulk deletes are permanent and need `confirm` set to the
media type being deleted.
"""

from http import HTTPStatus as HTTP  # noqa: N814
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import image_cache
from app.models import MediaTypes
from app.providers import credentials
from app.services import metadata_resolution
from config.server_port import (
    DEFAULT_SERVER_PORT,
    SERVER_PORT_ENV,
    ServerPortError,
    clear_saved_port,
    save_server_port,
)
from users import cache_management
from users import views as user_views
from users.metadata_views import (
    PROVIDER_DEFAULT_MEDIA_TYPES,
    _provider_default_field,
    _provider_summary,
    _provider_view,
)
from users.models import AnimeLibraryModeChoices
from users.server_port_views import _environment_override_active, server_port_context

from .contract_serializers import DetailErrorSerializer

_SUPERUSER_403 = OpenApiResponse(
    DetailErrorSerializer, description="Superusers only (instance-wide setting)."
)
_SUPERUSER_DETAIL = {"detail": "Only a superuser can change instance settings."}


def _not_superuser(user):
    if user.is_superuser:
        return None
    return Response(_SUPERUSER_DETAIL, status=HTTP.FORBIDDEN)


def _demo(user):
    if user.is_demo:
        return Response(
            {"detail": "This section is view-only for demo accounts."},
            status=HTTP.FORBIDDEN,
        )
    return None


def _data(request):
    return request.data if isinstance(request.data, dict) else {}


# --- Metadata providers ------------------------------------------------------


class MetadataProvidersView(drf_views.APIView):
    """Provider credentials (masked) and the default provider per media type."""

    @extend_schema(
        operation_id="getMetadataProviders",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request):
        """Return provider groups, each field's source and masked preview."""
        user = request.user
        groups = []
        for group in credentials.GROUP_ORDER:
            providers = sorted(
                (
                    _provider_view(spec, user)
                    for spec in credentials.REGISTRY.values()
                    if spec.group == group
                ),
                key=lambda provider: provider["label"].casefold(),
            )
            if providers:
                groups.append(
                    {
                        "key": group,
                        "label": credentials.GROUP_LABELS[group],
                        "description": credentials.GROUP_DESCRIPTIONS[group],
                        "providers": providers,
                    },
                )
        return Response(
            {
                "can_edit_instance": user.is_superuser,
                "groups": groups,
                "defaults": _provider_summary(user),
                "anime_library_mode": user.anime_library_mode,
                "anime_library_mode_choices": list(AnimeLibraryModeChoices.values),
            },
            status=HTTP.OK,
        )


def _spec_or_404(slug):
    spec = credentials.get_spec(slug)
    if spec is None:
        return None, Response({"detail": "Unknown provider."}, status=HTTP.NOT_FOUND)
    return spec, None


def _values(data, fields):
    values = {}
    for field in fields:
        value = data.get(field.name, "")
        if not isinstance(value, str):
            msg = f"{field.name} must be a string."
            raise TypeError(msg)
        values[field.name] = value.strip()
    return values


class ProviderInstanceCredentialView(drf_views.APIView):
    """Set or remove a provider's instance-wide credentials (superusers)."""

    @extend_schema(
        operation_id="setProviderInstanceCredentials",
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: DetailErrorSerializer,
            403: _SUPERUSER_403,
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, slug):
        """Save the fields sent; fields set by the environment are kept."""
        if denied := _not_superuser(request.user):
            return denied
        spec, error = _spec_or_404(slug)
        if error:
            return error
        try:
            values = _values(_data(request), spec.fields)
        except TypeError as value_error:
            return Response({"detail": str(value_error)}, status=HTTP.BAD_REQUEST)
        for field in spec.fields:
            if credentials.env_value(field):
                values.pop(field.name, None)
        if spec.validator is not None and any(values.values()):
            message = spec.validator(values)
            if message:
                return Response(
                    {"detail": f"{spec.label}: {message}"}, status=HTTP.BAD_REQUEST
                )
        credentials.set_instance(slug, values, actor=request.user)
        return Response(_provider_view(spec, request.user), status=HTTP.OK)

    @extend_schema(
        operation_id="clearProviderInstanceCredentials",
        responses={204: None, 403: _SUPERUSER_403, 404: DetailErrorSerializer},
    )
    def delete(self, request, slug):
        """Remove the instance-wide credentials."""
        if denied := _not_superuser(request.user):
            return denied
        _spec, error = _spec_or_404(slug)
        if error:
            return error
        credentials.clear_instance(slug)
        return Response(status=HTTP.NO_CONTENT)


class ProviderPersonalCredentialView(drf_views.APIView):
    """Set or remove the user's own key for a provider (empty values remove it)."""

    @extend_schema(
        operation_id="setProviderPersonalCredentials",
        request=OpenApiTypes.OBJECT,
        responses={
            200: OpenApiTypes.OBJECT,
            400: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, slug):
        """Save the personal fields sent."""
        spec, error = _spec_or_404(slug)
        if error:
            return error
        if not spec.user_scope:
            return Response(
                {"detail": "This provider takes no personal key."},
                status=HTTP.NOT_FOUND,
            )
        try:
            values = _values(_data(request), spec.personal_fields())
        except TypeError as value_error:
            return Response({"detail": str(value_error)}, status=HTTP.BAD_REQUEST)
        if spec.validator is not None and any(values.values()):
            message = spec.validator(values)
            if message:
                return Response(
                    {"detail": f"{spec.label}: {message}"}, status=HTTP.BAD_REQUEST
                )
        credentials.set_user(slug, request.user, values)
        return Response(_provider_view(spec, request.user), status=HTTP.OK)


class DefaultProviderRequestSerializer(serializers.Serializer):
    """The provider new titles of this type use."""

    source = serializers.CharField()
    anime_library_mode = serializers.ChoiceField(
        choices=list(AnimeLibraryModeChoices.values),
        required=False,
        help_text="anime only.",
    )


class DefaultProviderSerializer(serializers.Serializer):
    """The saved default."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    anime_needing_conversion = serializers.IntegerField(
        help_text=(
            "anime: tracked titles still in the old shape; convert them with "
            "POST user/anime-library/convert/."
        ),
    )


class DefaultProviderView(drf_views.APIView):
    """Choose the default metadata provider for TV, anime or books."""

    @extend_schema(
        operation_id="setDefaultMetadataProvider",
        request=DefaultProviderRequestSerializer,
        responses={
            200: DefaultProviderSerializer,
            400: DetailErrorSerializer,
            403: DetailErrorSerializer,
            404: DetailErrorSerializer,
        },
    )
    def put(self, request, media_type):
        """Save the provider (and, for anime, the library shape)."""
        if media_type not in PROVIDER_DEFAULT_MEDIA_TYPES:
            return Response(
                {"detail": "This media type has no default provider."},
                status=HTTP.NOT_FOUND,
            )
        if denied := _demo(request.user):
            return denied
        data = _data(request)
        source = data.get("source")
        valid = {
            choice.value
            for choice in metadata_resolution.available_metadata_sources(media_type)
        }
        if source not in valid:
            return Response(
                {"detail": "That provider isn't available for this media type."},
                status=HTTP.BAD_REQUEST,
            )
        mode = data.get("anime_library_mode")
        if mode is not None and (
            media_type != MediaTypes.ANIME.value
            or mode not in AnimeLibraryModeChoices.values
        ):
            return Response(
                {"detail": "anime_library_mode applies to anime only."},
                status=HTTP.BAD_REQUEST,
            )
        user = request.user
        updates = []
        field = _provider_default_field(media_type)
        if getattr(user, field) != source:
            setattr(user, field, source)
            updates.append(field)
        if mode is not None and user.anime_library_mode != mode:
            user.anime_library_mode = mode
            updates.append("anime_library_mode")
        if updates:
            user.save(update_fields=updates)
        needing = 0
        if media_type == MediaTypes.ANIME.value:
            from app.tasks_anime_library_repair import anime_rows_needing_conversion

            needing = len(anime_rows_needing_conversion(user))
        return Response(
            {"media_type": media_type, "source": source, "anime_needing_conversion": needing},
            status=HTTP.OK,
        )


# --- Image cache and server port (instance) ---------------------------------


class ImageCacheSerializer(serializers.Serializer):
    """External image caching."""

    enabled = serializers.BooleanField()
    days = serializers.IntegerField(help_text="7, 15 or 30.")
    cached_images = serializers.IntegerField()
    cached_bytes = serializers.IntegerField()


class ImageCacheUpdateSerializer(serializers.Serializer):
    """Fields to change."""

    enabled = serializers.BooleanField(required=False)
    days = serializers.ChoiceField(choices=[7, 15, 30], required=False)


def _image_cache_payload():
    stats = image_cache.cache_stats()
    return {
        "enabled": image_cache.is_enabled(),
        "days": image_cache.retention_days(),
        "cached_images": stats.get("count", 0),
        "cached_bytes": stats.get("bytes", 0),
    }


class ImageCacheView(drf_views.APIView):
    """Read or change external image caching."""

    @extend_schema(operation_id="getImageCache", responses={200: ImageCacheSerializer})
    def get(self, request):
        """Return the setting and what is cached."""
        return Response(_image_cache_payload(), status=HTTP.OK)

    @extend_schema(
        operation_id="updateImageCache",
        request=ImageCacheUpdateSerializer,
        responses={200: ImageCacheSerializer, 400: DetailErrorSerializer, 403: _SUPERUSER_403},
    )
    def patch(self, request):
        """Turn caching on or off, or change how long images are kept."""
        if denied := _not_superuser(request.user):
            return denied
        data = _data(request)
        enabled = data.get("enabled")
        days = data.get("days")
        if (enabled is not None and not isinstance(enabled, bool)) or (
            days is not None and (isinstance(days, bool) or days not in (7, 15, 30))
        ):
            return Response(
                {"detail": "enabled is a boolean; days is 7, 15 or 30."},
                status=HTTP.BAD_REQUEST,
            )
        if enabled is not None:
            image_cache.set_enabled(enabled)
        if days is not None:
            image_cache.set_retention_days(days)
        return Response(_image_cache_payload(), status=HTTP.OK)


class ImageCacheClearSerializer(serializers.Serializer):
    """What the purge removed."""

    removed_count = serializers.IntegerField()
    removed_bytes = serializers.IntegerField()


class ImageCacheClearView(drf_views.APIView):
    """Delete every cached image."""

    @extend_schema(
        operation_id="clearImageCache",
        request=None,
        responses={200: ImageCacheClearSerializer, 403: _SUPERUSER_403},
    )
    def post(self, request):
        """Purge the cache; images are fetched again when next shown."""
        if denied := _not_superuser(request.user):
            return denied
        summary = image_cache.clear_cache()
        return Response(
            {
                "removed_count": summary.get("removed_count", 0),
                "removed_bytes": summary.get("removed_bytes", 0),
            },
            status=HTTP.OK,
        )


class ServerPortSerializer(serializers.Serializer):
    """The port Floppy listens on."""

    effective_port = serializers.IntegerField(allow_null=True)
    source = serializers.CharField(allow_null=True)
    saved_port = serializers.IntegerField(allow_null=True)
    environment_port = serializers.IntegerField(allow_null=True)
    runtime_port = serializers.IntegerField(
        allow_null=True, help_text="The port the running server uses."
    )
    default_port = serializers.IntegerField()
    environment_override = serializers.BooleanField(
        help_text="The environment variable sets the port; it cannot be saved here.",
    )
    config_error = serializers.CharField(allow_blank=True)
    restart_required = serializers.BooleanField()


class ServerPortUpdateSerializer(serializers.Serializer):
    """The port to use after the next restart."""

    port = serializers.IntegerField(min_value=1, max_value=65535)


def _server_port_payload():
    context = server_port_context()
    status = context["server_port_status"]
    effective = status.effective_port if status else None
    return {
        "effective_port": effective,
        "source": status.source if status else None,
        "saved_port": status.saved_port if status else None,
        "environment_port": status.environment_port if status else None,
        "runtime_port": context["runtime_port"],
        "default_port": DEFAULT_SERVER_PORT,
        "environment_override": context["environment_override"],
        "config_error": context["server_port_config_error"] or "",
        "restart_required": bool(
            context["runtime_port"] and effective and context["runtime_port"] != effective
        ),
    }


class ServerPortView(drf_views.APIView):
    """Read, save or reset the server port (applies after a restart)."""

    @extend_schema(operation_id="getServerPort", responses={200: ServerPortSerializer})
    def get(self, request):
        """Return the port and where it comes from."""
        return Response(_server_port_payload(), status=HTTP.OK)

    @extend_schema(
        operation_id="setServerPort",
        request=ServerPortUpdateSerializer,
        responses={
            200: ServerPortSerializer,
            400: DetailErrorSerializer,
            403: _SUPERUSER_403,
            409: OpenApiResponse(
                DetailErrorSerializer,
                description=f"{SERVER_PORT_ENV} sets the port; change it there.",
            ),
        },
    )
    def put(self, request):
        """Save the port; restart Floppy to apply it."""
        if denied := _not_superuser(request.user):
            return denied
        if _environment_override_active():
            return Response(
                {
                    "detail": (
                        f"{SERVER_PORT_ENV} controls the server port for this instance."
                    ),
                    "code": "conflict",
                },
                status=HTTP.CONFLICT,
            )
        try:
            save_server_port(str(_data(request).get("port", "")))
        except ServerPortError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return Response(_server_port_payload(), status=HTTP.OK)

    @extend_schema(
        operation_id="resetServerPort",
        responses={200: ServerPortSerializer, 400: DetailErrorSerializer, 403: _SUPERUSER_403},
    )
    def delete(self, request):
        """Remove the saved port; the environment or default applies after a restart."""
        if denied := _not_superuser(request.user):
            return denied
        try:
            clear_saved_port()
        except ServerPortError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return Response(_server_port_payload(), status=HTTP.OK)


class LogsView(drf_views.APIView):
    """Download recent application logs with secrets redacted (superusers)."""

    @extend_schema(
        operation_id="downloadLogs",
        responses={(200, "text/plain"): OpenApiTypes.STR, 403: _SUPERUSER_403},
    )
    def get(self, request):
        """Return the logs as a text file."""
        if denied := _not_superuser(request.user):
            return denied
        from app.log_safety import redact_secrets

        log_path = Path(settings.LOG_FILE)
        backups = sorted(
            log_path.parent.glob(f"{log_path.name}.*"),
            key=lambda path: int(path.suffix[1:]) if path.suffix[1:].isdigit() else 0,
            reverse=True,
        )
        raw_logs = "".join(
            path.read_text(encoding="utf-8", errors="replace")
            for path in [*backups, log_path]
            if path.exists()
        )
        response = HttpResponse(redact_secrets(raw_logs), content_type="text/plain")
        filename = f"floppy-logs-{timezone.localtime():%Y%m%d-%H%M%S}.txt"
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        response["Cache-Control"] = "no-store"
        return response


# --- The user's own maintenance ---------------------------------------------


class TmdbProxySerializer(serializers.Serializer):
    """Whether TMDB requests go through the user's proxy."""

    configured = serializers.BooleanField()


class TmdbProxyRequestSerializer(serializers.Serializer):
    """The proxy URL; stored encrypted and never returned."""

    url = serializers.CharField()


class TmdbProxyView(drf_views.APIView):
    """Route this user's TMDB requests through a proxy."""

    @extend_schema(operation_id="getTmdbProxy", responses={200: TmdbProxySerializer})
    def get(self, request):
        """Say whether a proxy is set (the URL is never returned)."""
        return Response({"configured": bool(request.user.tmdb_proxy_url)}, status=HTTP.OK)

    @extend_schema(
        operation_id="setTmdbProxy",
        request=TmdbProxyRequestSerializer,
        responses={200: TmdbProxySerializer, 400: DetailErrorSerializer},
    )
    def put(self, request):
        """Store the proxy URL, encrypted."""
        from integrations.imports.helpers import encrypt

        url = _data(request).get("url")
        if not isinstance(url, str) or not url.strip().startswith(("http://", "https://")):
            return Response(
                {"detail": "url must be an http(s) proxy URL."},
                status=HTTP.BAD_REQUEST,
            )
        request.user.tmdb_proxy_url = encrypt(url.strip())
        request.user.save(update_fields=["tmdb_proxy_url"])
        cache.delete("tmdb_proxy_url")
        return Response({"configured": True}, status=HTTP.OK)

    @extend_schema(operation_id="clearTmdbProxy", responses={204: None})
    def delete(self, request):
        """Stop using the proxy."""
        request.user.tmdb_proxy_url = ""
        request.user.save(update_fields=["tmdb_proxy_url"])
        cache.delete("tmdb_proxy_url")
        return Response(status=HTTP.NO_CONTENT)


_CACHE_CLEARERS = {
    "search": lambda _user: cache_management.clear_search_cache(),
    "history": lambda user: cache_management.clear_history_cache_for_user(user.id),
    "statistics": lambda user: cache_management.clear_statistics_cache_for_user(user.id),
    "discover": lambda user: cache_management.clear_discover_cache_for_user(user.id),
}


class CacheClearRequestSerializer(serializers.Serializer):
    """Which caches to clear; omit for all."""

    caches = serializers.ListField(
        child=serializers.ChoiceField(choices=list(_CACHE_CLEARERS)),
        required=False,
        help_text="`search` is shared by the instance; the others are this user's.",
    )


class CacheClearSerializer(serializers.Serializer):
    """Entries removed per cache."""

    cleared = serializers.DictField(child=serializers.IntegerField())


class CacheClearView(drf_views.APIView):
    """Clear cached search results and this user's history, statistics, Discover."""

    @extend_schema(
        operation_id="clearCaches",
        request=CacheClearRequestSerializer,
        responses={200: CacheClearSerializer, 400: DetailErrorSerializer},
    )
    def post(self, request):
        """Clear the caches named, or all."""
        names = _data(request).get("caches") or list(_CACHE_CLEARERS)
        if not isinstance(names, list) or any(name not in _CACHE_CLEARERS for name in names):
            return Response(
                {"detail": f"caches must be a list of {', '.join(_CACHE_CLEARERS)}."},
                status=HTTP.BAD_REQUEST,
            )
        cleared = {name: _CACHE_CLEARERS[name](request.user) for name in dict.fromkeys(names)}
        return Response({"cleared": cleared}, status=HTTP.OK)


class BulkDeleteRequestSerializer(serializers.Serializer):
    """What to delete permanently."""

    media_type = serializers.ChoiceField(choices=list(user_views.DELETABLE_MEDIA_TYPES))
    confirm = serializers.CharField(help_text="Must equal media_type.")
    source = serializers.CharField(
        required=False,
        help_text="Only what this import source added (e.g. `lastfm`).",
    )
    delete_metadata = serializers.BooleanField(
        required=False,
        help_text="Also remove catalog entries no one tracks any more (whole type only).",
    )


class BulkDeleteResultSerializer(serializers.Serializer):
    """What was deleted."""

    deleted = serializers.IntegerField()
    metadata_deleted = serializers.IntegerField()


class ImportSourceSummarySerializer(serializers.Serializer):
    """Rows an import source added, per media type."""

    media_type = serializers.CharField()
    source = serializers.CharField()
    count = serializers.IntegerField()


class BulkDeleteSummarySerializer(serializers.Serializer):
    """What can be deleted by import source."""

    import_sources = ImportSourceSummarySerializer(many=True)


class LibraryBulkDeleteView(drf_views.APIView):
    """Permanently delete a whole media type, or what one import source added."""

    @extend_schema(
        operation_id="getBulkDeleteSummary",
        responses={200: BulkDeleteSummarySerializer},
    )
    def get(self, request):
        """Return the rows each import source added, per media type."""
        return Response(
            {"import_sources": user_views._import_source_media_summary(request.user)},
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="bulkDeleteLibrary",
        request=BulkDeleteRequestSerializer,
        responses={
            200: BulkDeleteResultSerializer,
            400: DetailErrorSerializer,
            403: DetailErrorSerializer,
        },
    )
    def post(self, request):
        """Delete; this cannot be undone."""
        if denied := _demo(request.user):
            return denied
        data = _data(request)
        media_type = data.get("media_type")
        if media_type not in user_views.DELETABLE_MEDIA_TYPES:
            return Response({"detail": "Unknown media type."}, status=HTTP.BAD_REQUEST)
        if data.get("confirm") != media_type:
            return Response(
                {"detail": "Set confirm to the media type to delete it permanently."},
                status=HTTP.BAD_REQUEST,
            )
        delete_metadata = data.get("delete_metadata", False)
        if not isinstance(delete_metadata, bool):
            return Response(
                {"detail": "delete_metadata must be a boolean."}, status=HTTP.BAD_REQUEST
            )
        source = data.get("source")
        if source is not None:
            if delete_metadata or not isinstance(source, str):
                return Response(
                    {"detail": "source is a string and cannot be combined with delete_metadata."},
                    status=HTTP.BAD_REQUEST,
                )
            try:
                deleted = user_views.delete_import_source_media(
                    request.user, media_type, source
                )
            except user_views.BulkDeleteError as error:
                return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
            return Response({"deleted": deleted, "metadata_deleted": 0}, status=HTTP.OK)
        result = user_views.delete_media_type(
            request.user, media_type, delete_metadata=delete_metadata
        )
        return Response(
            {"deleted": result["item_count"], "metadata_deleted": result["metadata_count"]},
            status=HTTP.OK,
        )
