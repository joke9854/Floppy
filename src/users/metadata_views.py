"""Settings > Metadata: manage provider credentials and provider defaults."""

import os

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from app import config, helpers, preflight
from app.models import MediaTypes, Sources
from app.providers import credentials
from app.services import metadata_resolution
from users.models import AnimeLibraryModeChoices

MASK_VISIBLE_CHARS = 4

# Media types with a stored per-user default provider (a `<type>_metadata_source_default`
# field on User). Other media types have no such field, so their modal is informational
# only: it still lists every supported source and links out to configure one, but there
# is nothing to save.
PROVIDER_DEFAULT_MEDIA_TYPES = (
    MediaTypes.TV.value,
    MediaTypes.ANIME.value,
    MediaTypes.BOOK.value,
)


def _provider_default_field(media_type):
    """Return the User field name storing the default provider for a media type."""
    return f"{media_type}_metadata_source_default"


def _settable_media_types(slug):
    """Return the provider-default media types a provider slug can be set for."""
    types = []
    for media_type in PROVIDER_DEFAULT_MEDIA_TYPES:
        sources = {
            source.value if isinstance(source, Sources) else str(source)
            for source in config.get_sources(media_type) or []
        }
        if slug in sources:
            types.append(media_type)
    return types


def _provider_summary(user):
    """Return one entry per enabled media type, showing its resolved provider.

    Every entry lists all sources the media type supports, whether or not each
    one is currently configured, so the modal can point at what's missing
    instead of just hiding it. A media type is only editable (has a working
    dropdown + Save) when it has a stored per-user default field.
    """
    summary = []
    for media_type in user.get_sidebar_media_types():
        all_sources = config.get_sources(media_type) or []
        if not all_sources:
            continue
        current = metadata_resolution.metadata_default_source(user, media_type)
        summary.append(
            {
                "media_type": media_type,
                "current_provider": current,
                "current_label": metadata_resolution.metadata_provider_label(current),
                "choices": [
                    {
                        "value": source.value,
                        "label": source.label,
                        "configured": metadata_resolution.provider_is_enabled(
                            source.value,
                        ),
                    }
                    for source in all_sources
                ],
                "configurable": media_type in PROVIDER_DEFAULT_MEDIA_TYPES,
            },
        )
    return summary


def _mask(value):
    """Return a preview that proves a value is stored without revealing it."""
    if not value:
        return ""
    if len(value) <= MASK_VISIBLE_CHARS:
        return "•" * len(value)
    return f"{'•' * 8}{value[-MASK_VISIBLE_CHARS:]}"


def _field_view(spec, field, user):
    """Return the template view-model for one credential field."""
    source = credentials.source_of(spec.slug, field.name, user)
    env = credentials.env_value(field)
    stored = credentials.instance_value(spec.slug, field.name)
    return {
        "name": field.name,
        "label": field.label,
        "secret": field.secret,
        "required": field.required,
        "placeholder": field.placeholder,
        "setting": field.setting,
        "source": source,
        "locked": bool(env),
        "preview": _mask(env or stored),
        "has_instance_value": bool(stored),
        "personal": field.name in {f.name for f in spec.personal_fields()},
        "has_personal_value": bool(credentials.user_value(spec, field, user)),
    }


def _provider_view(spec, user):
    """Return the template view-model for one provider row."""
    fields = [_field_view(spec, field, user) for field in spec.fields]
    sources = {field["source"] for field in fields if field["source"]}
    if credentials.has_user_value(spec.slug, user):
        status = credentials.SOURCE_USER
    elif credentials.SOURCE_ENV in sources:
        status = credentials.SOURCE_ENV
    elif credentials.SOURCE_DB in sources:
        status = credentials.SOURCE_DB
    elif credentials.SOURCE_DEFAULT in sources:
        status = credentials.SOURCE_DEFAULT
    else:
        status = ""
    return {
        "slug": spec.slug,
        "label": spec.label,
        "logo_slug": spec.logo_slug or spec.slug,
        "description": spec.description,
        "docs_url": spec.docs_url,
        "user_scope": spec.user_scope,
        "configured": credentials.is_configured(spec.slug, user),
        "status": status,
        "fields": fields,
        "personal_fields": [field for field in fields if field["personal"]],
        "locked": all(field["locked"] for field in fields),
        "has_instance_value": any(field["has_instance_value"] for field in fields),
        "settable_media_types": _settable_media_types(spec.slug),
    }


def _promote_command(username):
    """Return the promote command for the environment Floppy is running in.

    Reuses app.preflight.in_container so a Podman install is not handed
    Docker-only advice, and the container name follows the same
    HOST_CONTAINERNAME convention the SQLite recovery page uses.
    """
    if preflight.in_container():
        container = os.environ.get("HOST_CONTAINERNAME", "floppy")
        return f"docker exec -it {container} python manage.py promote_superuser {username}"
    return f"python src/manage.py promote_superuser {username}"


@require_GET
def metadata_settings(request):
    """Render the metadata provider credentials page."""
    user = request.user
    # Every provider takes a personal key now, so "who can set it" no longer
    # separates anything; grouping by what the provider does is what is left.
    can_edit_instance = user.is_superuser
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

    context = {
        "credential_groups": groups,
        "can_edit_instance": can_edit_instance,
        "provider_summary": _provider_summary(user),
        "anime_library_mode_choices": AnimeLibraryModeChoices.choices,
        "anime_shape_prompt_count": request.session.pop(
            "anime_shape_prompt_count",
            None,
        ),
    }
    if not can_edit_instance:
        # Floppy's setup never flags anyone, so the owner of a fresh install is
        # usually not a superuser and has no way to discover that.
        context["instance_has_superuser"] = (
            get_user_model().objects.filter(is_superuser=True).exists()
        )
        context["in_container"] = preflight.in_container()
        context["promote_command"] = _promote_command(user.username)
    return render(request, "users/metadata.html", context)


@helpers.answers_json
@require_POST
def set_media_type_provider(request, media_type):
    """Save the current user's preferred metadata provider for one media type."""
    if media_type not in PROVIDER_DEFAULT_MEDIA_TYPES:
        return HttpResponse(status=404)
    if request.user.is_demo:
        messages.error(request, "This section is view-only for demo accounts.")
        return redirect("metadata_settings")

    source = request.POST.get("source", "")
    valid_sources = {
        choice.value
        for choice in metadata_resolution.available_metadata_sources(media_type)
    }
    if source not in valid_sources:
        messages.error(request, "That provider isn't available for this media type.")
        return redirect("metadata_settings")

    field = _provider_default_field(media_type)
    if getattr(request.user, field) != source:
        setattr(request.user, field, source)
        request.user.save(update_fields=[field])

        if media_type == MediaTypes.ANIME.value:
            # Switching provider only decides the shape of newly added shows.
            # Existing ones are left alone unless the user asks, because the
            # MAL-to-series mapping is N:1 and cannot be re-derived in bulk.
            from app.tasks_anime_library_repair import anime_rows_needing_conversion

            convertible = anime_rows_needing_conversion(request.user)
            if convertible and helpers.wants_json(request):
                # The web app asks right away; the page reads it from the session.
                request.answer_extra = {"anime_shape_prompt_count": len(convertible)}
            elif convertible:
                request.session["anime_shape_prompt_count"] = len(convertible)

    if media_type == MediaTypes.ANIME.value:
        anime_library_mode = request.POST.get("anime_library_mode")
        if (
            anime_library_mode in AnimeLibraryModeChoices.values
            and request.user.anime_library_mode != anime_library_mode
        ):
            request.user.anime_library_mode = anime_library_mode
            request.user.save(update_fields=["anime_library_mode"])

    messages.success(request, "Metadata provider updated.")
    return redirect("metadata_settings")


def _spec_or_none(slug):
    """Return the registry entry for a slug, or None."""
    return credentials.get_spec(slug)


@helpers.answers_json
@require_POST
def save_provider_credential(request, slug):
    """Store instance-wide credentials for a provider."""
    if not request.user.is_superuser:
        return HttpResponse(status=403)

    spec = _spec_or_none(slug)
    if spec is None:
        return HttpResponse(status=404)

    values = {
        field.name: request.POST.get(field.name, "").strip() for field in spec.fields
    }
    # A locked field is rendered read-only, so never let a post overwrite it.
    for field in spec.fields:
        if credentials.env_value(field):
            values.pop(field.name, None)

    if spec.validator is not None and any(values.values()):
        error = spec.validator(values)
        if error:
            messages.error(request, f"{spec.label}: {error}")
            return redirect("metadata_settings")

    credentials.set_instance(slug, values, actor=request.user)
    messages.success(request, f"{spec.label} credentials saved.")
    return redirect("metadata_settings")


@helpers.answers_json
@require_POST
def clear_provider_credential(request, slug):
    """Remove the instance-wide credentials for a provider."""
    if not request.user.is_superuser:
        return HttpResponse(status=403)

    spec = _spec_or_none(slug)
    if spec is None:
        return HttpResponse(status=404)

    credentials.clear_instance(slug)
    messages.success(request, f"{spec.label} credentials removed.")
    return redirect("metadata_settings")


@helpers.answers_json
@require_POST
def save_personal_credential(request, slug):
    """Store the current user's personal credentials for a provider."""
    spec = _spec_or_none(slug)
    if spec is None or not spec.user_scope:
        return HttpResponse(status=404)

    values = {
        field.name: request.POST.get(field.name, "").strip()
        for field in spec.personal_fields()
    }
    if spec.validator is not None and any(values.values()):
        error = spec.validator(values)
        if error:
            messages.error(request, f"{spec.label}: {error}")
            return redirect("metadata_settings")

    credentials.set_user(slug, request.user, values)
    if any(values.values()):
        messages.success(request, f"Your {spec.label} key was saved.")
    else:
        messages.success(request, f"Your {spec.label} key was removed.")
    return redirect("metadata_settings")
