"""Contains views for importing and exporting media data from various sources."""

import base64
import binascii
import hmac
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from http import HTTPStatus
from urllib.parse import unquote

import requests
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required, login_required
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseNotFound,
    JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

import users
from app import helpers as app_helpers
from app import image_cache
from app.log_safety import exception_summary
from app.models import TV, Item, MediaTypes, Movie, Sources
from app.providers import credentials, services
from integrations import (
    audiobookshelf_cover as abs_cover_proxy,
)
from integrations import (
    connections,
    exports,
    stremio_catalog,
    stremio_queue,
    tasks,
)
from integrations import plex as plex_api
from integrations import plex_cover as plex_cover_proxy
from integrations.connections import (
    _ensure_storyteller_schedule,
    _run_with_lock_retry,
)
from integrations.imports import anilist, helpers, mdblist, simkl, trakt
from integrations.imports.storyteller import (
    StorytellerClient,
    StorytellerClientError,
)
from integrations.match_corrections import (
    InvalidMatchCorrectionError,
    MissingEpisodeMappingError,
    StaleCorrectionPreviewError,
    apply_match_correction,
    preview_match_correction,
)
from integrations.models import (
    AudiobookshelfAccount,
    ExternalReference,
    ExternalReferenceReviewStatus,
    MDBListAccount,
    PlexAccount,
    PlexWebhookShare,
    StateConflict,
    StateConflictStatus,
    StorytellerAccount,
    SyncBinding,
)
from integrations.plex_watchlist import (
    WATCHLIST_SYNC_INTERVAL_MINUTES,
)
from integrations.upload_staging import (
    build_staged_zip,
    discard_staged_upload,
    enqueue_staged_task,
    stage_uploaded_file,
    staged_payload_is_zip,
)
from integrations.webhooks.plex import extract_plex_webhook_usernames

logger = logging.getLogger(__name__)
JELLYFIN_PLAYBACK_REPORTING_MAX_UPLOAD_BYTES = 50 * 1024 * 1024
TRAKT_DEVICE_SESSION_KEY = "trakt_device_auth"

# Names that moved to (or are used through) integrations.connections. Tests and
# older callers patch/import them through integrations.views, so keep them here.
_ensure_jellyfin_pull_schedule = connections._ensure_jellyfin_pull_schedule
_ensure_jellyfin_push_schedule = connections._ensure_jellyfin_push_schedule
AudiobookshelfClient = connections.AudiobookshelfClient
JellyfinClient = connections.JellyfinClient
KoitoAccount = connections.KoitoAccount
KoreaderClient = connections.KoreaderClient
RadarrClient = connections.RadarrClient
SonarrClient = connections.SonarrClient
gpodder_api = connections.gpodder_api
koito_api = connections.koito_api
lastfm_api = connections.lastfm_api
psn_api = connections.psn_api
stremio = connections.stremio
xbox_api = connections.xbox_api


def _stage_upload_or_message(request, upload, label="upload"):
    """Stage an upload and report storage failures without returning a 500."""
    try:
        return str(stage_uploaded_file(upload))
    except OSError:
        logger.exception("Could not stage %s for background import", label)
        messages.error(
            request,
            "The upload could not be queued. Check available disk space and try again.",
        )
        return None


def _stage_uploads_or_message(request, uploads, label="upload"):
    """Stage multiple uploads and roll back earlier files on failure."""
    staged = []
    for upload in uploads:
        path = _stage_upload_or_message(request, upload, label)
        if path is None:
            for staged_path in staged:
                discard_staged_upload(staged_path)
            return None
        staged.append(path)
    return staged


def _queue_staged_task_or_message(
    request,
    task,
    *args,
    staged_paths=(),
    **kwargs,
):
    """Queue a staged task and turn broker failures into a user message."""
    try:
        return enqueue_staged_task(
            task,
            *args,
            staged_paths=staged_paths,
            **kwargs,
        )
    except Exception:
        logger.exception("Could not queue background import task")
        messages.error(
            request,
            "The import could not be queued. Check the worker and try again.",
        )
        return False


def _queue_task_quietly(task, *args, **kwargs):
    """Queue a task, logging (not raising) on broker failure.

    For call sites with no `messages` flow to surface the failure through
    (webhook receivers, JSON polling endpoints).
    """
    try:
        task.delay(*args, **kwargs)
    except Exception:
        logger.exception("Could not queue background task")
        return False
    return True


def _integration_redirect(request, *, connected_slug=None, next_url=None):
    """Redirect back to `next` (e.g. the onboarding wizard) if present.

    Falls back to `import_data`, the normal Settings destination. When
    `connected_slug` is given, records it on the user's onboarding progress
    so the setup wizard's queue drops that source on the next request.
    """
    if connected_slug:
        user = request.user
        if connected_slug not in user.onboarding_connected_sources:
            user.onboarding_connected_sources = [*user.onboarding_connected_sources, connected_slug]
            user.save(update_fields=["onboarding_connected_sources"])
    destination = next_url or request.POST.get("next") or request.GET.get("next")
    return redirect(destination or "import_data")


def _consume_oauth_state(request, provider):
    """Consume a provider OAuth state value and reject missing or replayed state."""
    state_token = request.GET.get("state")
    if not state_token:
        logger.warning("%s OAuth callback missing state parameter", provider)
        messages.error(
            request,
            f"Invalid or expired {provider} authorization request.",
        )
        return None

    state_data = request.session.pop(state_token, None)
    if not isinstance(state_data, dict):
        logger.warning("%s OAuth callback state not found in session", provider)
        messages.error(
            request,
            f"Invalid or expired {provider} authorization request.",
        )
        return None

    return state_data


def _save_plex_usernames(user, raw_usernames):
    """Persist de-duplicated Plex usernames for webhook filtering."""
    if raw_usernames is None:
        return

    username_list = [u.strip() for u in raw_usernames.split(",") if u.strip()]
    seen = set()
    deduplicated = [
        u for u in username_list if not (u.lower() in seen or seen.add(u.lower()))
    ]
    cleaned_usernames = ", ".join(deduplicated)
    if cleaned_usernames != user.plex_usernames:
        user.plex_usernames = cleaned_usernames
        user.save(update_fields=["plex_usernames"])


@require_POST
def trakt_oauth(request):
    """View for initiating Trakt OAuth2 authorization flow."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_trakt_private"),
    )
    if not app_helpers.supports_oauth_redirect(redirect_uri):
        # Trakt refuses non-HTTPS callbacks, so this instance can only connect
        # through the device code flow (#681).
        return _start_trakt_device_flow(request)

    url = "https://trakt.tv/oauth/authorize"
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "redirect_uri": redirect_uri,
        "return_to": request.POST.get("next"),
    }
    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state
    client_id = credentials.get("trakt", "client_id")
    return redirect(
        f"{url}?client_id={client_id}&redirect_uri={redirect_uri}&response_type=code&state={state_token}",
    )


def _finish_trakt_connection(request, oauth_result, state_data):
    """Encrypt the refresh token, then queue or schedule the Trakt import."""
    enc_token = helpers.encrypt(oauth_result["refresh_token"])

    frequency = state_data["frequency"]
    mode = state_data["mode"]
    import_time = state_data["time"]

    if frequency == "once":
        tasks.import_trakt.delay(
            token=enc_token,
            user_id=request.user.id,
            mode=mode,
            username=oauth_result["username"],
        )
        messages.info(request, "The task to import media from Trakt has been queued.")
    else:
        helpers.create_import_schedule(
            oauth_result["username"],
            request,
            mode,
            frequency,
            import_time,
            "Trakt",
            token=enc_token,
        )


def _start_trakt_device_flow(request):
    """Mint a Trakt device code and send the user to the code screen."""
    try:
        device = trakt.request_device_code()
    except helpers.MediaImportError as error:
        messages.error(request, str(error))
        return _integration_redirect(request)

    request.session[TRAKT_DEVICE_SESSION_KEY] = {
        "device_code": device["device_code"],
        "user_code": device["user_code"],
        "verification_url": device["verification_url"],
        "interval": device["interval"],
        "expires_at": (
            timezone.now() + timedelta(seconds=int(device["expires_in"]))
        ).isoformat(),
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "return_to": request.POST.get("next"),
    }
    return redirect("trakt_device_verify")


def _trakt_device_state(request):
    """Return the pending device authorization, or None if gone or expired."""
    state = request.session.get(TRAKT_DEVICE_SESSION_KEY)
    if not isinstance(state, dict):
        return None
    expires_at = parse_datetime(state.get("expires_at") or "")
    if expires_at is None or timezone.now() >= expires_at:
        return None
    return state


@require_GET
def trakt_device_verify(request):
    """Show the Trakt device code the user must enter at trakt.tv/activate."""
    state = _trakt_device_state(request)
    if state is None:
        request.session.pop(TRAKT_DEVICE_SESSION_KEY, None)
        messages.error(request, "The Trakt authorization code expired. Start again.")
        return _integration_redirect(request)

    return render(
        request,
        "integrations/trakt_device_code.html",
        {
            "user_code": state["user_code"],
            "verification_url": state["verification_url"],
            "interval": state["interval"],
            "poll_url": reverse("trakt_device_poll"),
            "cancel_url": reverse("import_data"),
        },
    )


def _htmx_redirect(location):
    """Tell HTMX to navigate away without swapping anything in."""
    return HttpResponse(status=HTTPStatus.NO_CONTENT, headers={"HX-Redirect": location})


@require_GET
def trakt_device_poll(request):
    """Poll Trakt once for the pending device authorization."""
    state = _trakt_device_state(request)
    if state is None:
        request.session.pop(TRAKT_DEVICE_SESSION_KEY, None)
        messages.error(request, "The Trakt authorization code expired. Start again.")
        return _htmx_redirect(reverse("import_data"))

    try:
        result = trakt.poll_device_token(state["device_code"])
    except helpers.MediaImportError as error:
        request.session.pop(TRAKT_DEVICE_SESSION_KEY, None)
        messages.error(request, str(error))
        return _htmx_redirect(reverse("import_data"))

    if result is None:
        return HttpResponse(status=HTTPStatus.NO_CONTENT)

    request.session.pop(TRAKT_DEVICE_SESSION_KEY, None)
    _finish_trakt_connection(request, result, state)
    redirect_response = _integration_redirect(
        request,
        connected_slug="trakt",
        next_url=state.get("return_to"),
    )
    return _htmx_redirect(redirect_response["Location"])


@require_GET
def import_trakt_private(request):
    """View for handling Trakt OAuth2 callback and scheduling private import."""
    state_data = _consume_oauth_state(request, "Trakt")
    if state_data is None:
        return _integration_redirect(request)

    redirect_uri = state_data.get("redirect_uri")
    oauth_callback = trakt.handle_oauth_callback(request, redirect_uri=redirect_uri)
    _finish_trakt_connection(request, oauth_callback, state_data)
    return _integration_redirect(
        request,
        connected_slug="trakt",
        next_url=state_data.get("return_to"),
    )


@require_POST
def import_trakt_public(request):
    """View for importing Trakt data using public username."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "Trakt username is required.")
        return _integration_redirect(request)

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]

    if frequency == "once":
        tasks.import_trakt.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
        )
        messages.info(request, "The task to import media from Trakt has been queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="Trakt",
        )
    return _integration_redirect(request, connected_slug="trakt")


@app_helpers.answers_json
@require_POST
def import_mdblist(request):
    """View for importing MDBList tracking data (watched, ratings, etc.)."""
    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]
    api_key = request.POST.get("api_key", "").strip()

    account = MDBListAccount.objects.filter(user=request.user).first()
    if api_key:
        try:
            mdblist.validate_api_key(api_key)
        except helpers.MediaImportError:
            messages.error(
                request,
                "Could not validate the MDBList API key. Check it and try again.",
            )
            return _integration_redirect(request)
        account, _ = MDBListAccount.objects.update_or_create(
            user=request.user,
            defaults={
                "api_key": helpers.encrypt(api_key),
                "connection_broken": False,
                "last_error_message": "",
            },
        )
    elif account is None:
        messages.error(request, "An MDBList API key is required.")
        return _integration_redirect(request)

    if frequency == "once":
        tasks.import_mdblist.delay(user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from MDBList has been queued.")
    else:
        helpers.create_import_schedule(
            username=request.user.username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="MDBList",
        )
    return _integration_redirect(request, connected_slug="mdblist")


@require_POST
def plex_connect(request):
    """Initiate Plex authentication via the pin-based flow."""
    redirect_uri = app_helpers.build_absolute_app_url(request, reverse("plex_callback"))
    state_token = secrets.token_urlsafe(16)

    try:
        pin = plex_api.create_pin()
    except plex_api.PlexClientError as exc:
        messages.error(request, f"Could not start Plex connection: {exc}")
        return _integration_redirect(request)
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, f"Unexpected Plex error: {exc}")
        return _integration_redirect(request)

    request.session[state_token] = {
        "plex_pin_id": pin["id"],
        "plex_pin_code": pin["code"],
        "return_to": request.POST.get("next"),
    }

    auth_url = plex_api.build_auth_url(
        pin["code"], f"{redirect_uri}?state={state_token}"
    )
    return redirect(auth_url)


@require_GET
def plex_callback(request):
    """Handle Plex auth callback and persist the token."""
    state_token = request.GET.get("state")
    state_data = request.session.pop(state_token, None)

    if not state_data:
        messages.error(request, "Invalid or expired Plex authorization request.")
        return _integration_redirect(request)

    return_to = state_data.get("return_to")

    pin_id = state_data.get("plex_pin_id")
    try:
        plex_token = plex_api.poll_pin(pin_id)
    except plex_api.PlexAuthError as exc:
        messages.error(request, f"Plex authorization failed: {exc}")
        return _integration_redirect(request, next_url=return_to)
    except plex_api.PlexClientError as exc:  # pragma: no cover - defensive
        messages.error(request, f"Could not complete Plex authorization: {exc}")
        return _integration_redirect(request, next_url=return_to)
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, f"Unexpected Plex response: {exc}")
        return _integration_redirect(request, next_url=return_to)

    try:
        account = plex_api.fetch_account(plex_token)
    except plex_api.PlexAuthError as exc:
        messages.error(request, f"Plex rejected the token: {exc}")
        return _integration_redirect(request, next_url=return_to)
    except plex_api.PlexClientError as exc:  # pragma: no cover - defensive
        messages.error(request, f"Could not read Plex account details: {exc}")
        return _integration_redirect(request, next_url=return_to)
    except Exception as exc:  # pragma: no cover - defensive
        messages.error(request, f"Unexpected Plex account response: {exc}")
        return _integration_redirect(request, next_url=return_to)

    sections: list[dict] = []
    try:
        sections = plex_api.list_sections(plex_token)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "Connected to Plex but could not fetch libraries: %s",
            exception_summary(exc),
        )
        messages.warning(
            request,
            "Connected to Plex, but could not load libraries yet. You can refresh from the import page.",
        )

    # Keep webhook allow list in sync
    username = (account.get("username") or "").strip()
    if username:
        existing = [
            u.strip()
            for u in (request.user.plex_usernames or "").split(",")
            if u.strip()
        ]
        if username.lower() not in [u.lower() for u in existing]:
            request.user.plex_usernames = ", ".join([*existing, username])
            request.user.save(update_fields=["plex_usernames"])

    defaults = {
        "plex_token": plex_token,
        "plex_username": account.get("username") or "",
        "plex_account_id": account.get("id") or "",
        "sections": sections,
        "sections_refreshed_at": timezone.now(),
    }

    if sections:
        defaults["server_name"] = sections[0].get("server_name")
        defaults["machine_identifier"] = sections[0].get("machine_identifier")

    _run_with_lock_retry(
        "connect Plex",
        lambda: PlexAccount.objects.update_or_create(
            user=request.user,
            defaults=defaults,
        ),
    )

    account_username = account.get("username") or "your Plex account"
    messages.success(request, f"Connected to Plex as {account_username}.")

    if return_to:
        # Arrived from the setup wizard: queue a sensible default import
        # rather than requiring a second visit to pick a library/mode.
        tasks.import_plex.delay(user_id=request.user.id, mode="new", library=["all"])

    return _integration_redirect(request, connected_slug="plex", next_url=return_to)


@require_POST
def plex_disconnect(request):
    """Remove stored Plex credentials."""
    connections.disconnect_plex(request.user)
    messages.info(request, "Disconnected Plex.")
    return redirect("import_data")


def _save_plex_content_kind(plex_account, library_content_kinds):
    """Persist per-library content-kind choices (auto/music/audiobook).

    Stored on the account rather than passed per-run so scheduled imports and
    the live webhook honor the same choice. Each entry is a
    "machine_identifier::section_id::content_kind" string.
    """
    changed = False
    for entry in library_content_kinds:
        try:
            machine_identifier, section_id, content_kind = entry.split("::", 2)
        except ValueError:
            continue
        changed = (
            plex_account.set_content_kind(machine_identifier, section_id, content_kind)
            or changed
        )
    if changed:
        plex_account.save(update_fields=["section_settings"])


@require_POST
def import_plex(request):
    """Queue a Plex history import for the current user."""
    plex_account = getattr(request.user, "plex_account", None)
    if not plex_account:
        messages.error(request, "Connect Plex before importing.")
        return redirect("import_data")

    library = request.POST.getlist("library") or ["all"]
    mode = request.POST.get("mode", "new")
    frequency = request.POST.get("frequency", "once")
    import_time = request.POST.get("time", "00:00")
    raw_usernames = request.POST.get("plex_usernames", "")
    library_content_kinds = request.POST.getlist("library_content_kind")

    _save_plex_usernames(request.user, raw_usernames)
    _save_plex_content_kind(plex_account, library_content_kinds)

    # The form offers daily or every two days; anything else ran every two.
    if frequency not in ("once", "daily"):
        frequency = "2days"
    try:
        connections.start_plex_import(
            request.user,
            libraries=library,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
        )
    except connections.IntegrationError as error:
        messages.error(request, error.web_message)
        return redirect("import_data")

    if mode == "watchlist":
        messages.info(
            request,
            (
                "Plex watchlist sync queued. "
                f"Recurring syncs will run every {WATCHLIST_SYNC_INTERVAL_MINUTES} minutes."
            ),
        )
    elif mode == "update_collection":
        messages.info(
            request, "The task to update collection metadata from Plex has been queued."
        )
    elif frequency != "once":
        messages.success(request, "Plex import task scheduled.")
    else:
        messages.info(request, "The task to import media from Plex has been queued.")
    return redirect("import_data")


@require_POST
def plex_disable_watchlist(request):
    """Disable recurring Plex watchlist sync for the current user."""
    try:
        connections.disable_plex_watchlist(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Disabled Plex watchlist sync.")
    return redirect("import_data")


@require_POST
def simkl_oauth(request):
    """View for initiating the SIMKL OAuth2 authorization flow."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_simkl_private"),
    )
    url = "https://simkl.com/oauth/authorize"

    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "redirect_uri": redirect_uri,
        "return_to": request.POST.get("next"),
    }
    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state

    return redirect(
        f"{url}?client_id={credentials.get("simkl", "client_id")}&redirect_uri={redirect_uri}&response_type=code&state={state_token}",
    )


@require_GET
def import_simkl_private(request):
    """View for getting the SIMKL OAuth2 token."""
    state_data = _consume_oauth_state(request, "SIMKL")
    if state_data is None:
        return _integration_redirect(request)

    redirect_uri = state_data.get("redirect_uri")
    oauth_callback = simkl.get_token(request, redirect_uri=redirect_uri)
    enc_token = helpers.encrypt(oauth_callback["access_token"])

    frequency = state_data["frequency"]
    mode = state_data["mode"]
    import_time = state_data["time"]
    return_to = state_data.get("return_to")

    if frequency == "once":
        tasks.import_simkl.delay(
            token=enc_token,
            user_id=request.user.id,
            mode=mode,
        )
        messages.info(request, "The task to import media from Simkl has been queued.")
    else:
        helpers.create_import_schedule(
            oauth_callback["username"],
            request,
            mode,
            frequency,
            import_time,
            "SIMKL",
            token=enc_token,
        )

    return _integration_redirect(request, connected_slug="simkl", next_url=return_to)


@app_helpers.answers_json
@require_POST
def import_mal(request):
    """View for importing anime and manga data from MyAnimeList."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "MyAnimeList username is required.")
        return _integration_redirect(request)

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_mal.delay(username=username, user_id=request.user.id, mode=mode)
        messages.info(
            request,
            "The task to import media from MyAnimeList has been queued.",
        )
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            username,
            request,
            mode,
            frequency,
            import_time,
            "MyAnimeList",
        )
    return _integration_redirect(request, connected_slug="myanimelist")


@require_POST
def anilist_oauth(request):
    """Initiate AniList OAuth flow."""
    redirect_uri = app_helpers.build_absolute_app_url(
        request,
        reverse("import_anilist_private"),
    )
    url = "https://anilist.co/api/v2/oauth/authorize"
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
        "redirect_uri": redirect_uri,
        "return_to": request.POST.get("next"),
    }

    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state

    return redirect(
        f"{url}?client_id={credentials.get("anilist", "client_id")}&redirect_uri={redirect_uri}&response_type=code&state={state_token}",
    )


@require_GET
def import_anilist_private(request):
    """View for getting the AniList OAuth2 token."""
    state_data = _consume_oauth_state(request, "AniList")
    if state_data is None:
        return _integration_redirect(request)

    redirect_uri = state_data.get("redirect_uri")
    oauth_callback = anilist.get_token(request, redirect_uri=redirect_uri)
    enc_token = helpers.encrypt(oauth_callback["access_token"])
    username = oauth_callback["username"]
    return_to = state_data.get("return_to")

    if not username:
        messages.error(request, "AniList username is required.")
        return _integration_redirect(request, next_url=return_to)

    frequency = state_data["frequency"]
    mode = state_data["mode"]
    import_time = state_data["time"]

    if frequency == "once":
        tasks.import_anilist.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
            token=enc_token,
        )
        messages.info(request, "AniList import queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="AniList",
            token=enc_token,
        )
    return _integration_redirect(request, connected_slug="anilist", next_url=return_to)


@require_POST
def import_anilist_public(request):
    """View for importing anime and manga data from AniList."""
    username = request.POST.get("user")
    if not username:
        messages.error(request, "AniList username is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]

    if frequency == "once":
        tasks.import_anilist.delay(
            user_id=request.user.id,
            mode=mode,
            username=username,
        )
        messages.info(request, "AniList import queued.")
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="AniList",
        )
    return redirect("import_data")


@app_helpers.answers_json
@require_POST
def import_kitsu(request):
    """View for importing anime and manga data from Kitsu by user ID."""
    kitsu_id = request.POST.get("user")
    if not kitsu_id:
        messages.error(request, "Kitsu user ID is required.")
        return _integration_redirect(request)

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_kitsu.delay(username=kitsu_id, user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from Kitsu has been queued.")
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            kitsu_id,
            request,
            mode,
            frequency,
            import_time,
            "Kitsu",
        )
    return _integration_redirect(request, connected_slug="kitsu")


@app_helpers.answers_json
@require_POST
def import_yamtrack(request):
    """View for importing a Floppy backup or an upstream Yamtrack CSV."""
    file = request.FILES.get("yamtrack_csv")

    if not file:
        messages.error(request, "A CSV file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "Floppy CSV")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_yamtrack,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="yamtrack")
    messages.info(
        request,
        "The task to import media from the CSV file has been queued.",
    )
    return _integration_redirect(request, connected_slug="yamtrack")


@app_helpers.answers_json
@require_POST
def import_clz(request):
    """View for importing a CLZ (Collectorz) CSV or XML export."""
    file = request.FILES.get("clz_export")

    if not file:
        messages.error(request, "A CLZ CSV or XML export is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "CLZ export")
    if staged_file is None:
        return _integration_redirect(request)

    media_type = (request.POST.get("clz_media_type") or "").strip() or None
    if media_type and media_type not in MediaTypes.values:
        discard_staged_upload(staged_file)
        messages.error(request, "Unknown media type for the CLZ import.")
        return _integration_redirect(request)

    if _queue_staged_task_or_message(
        request,
        tasks.import_clz,
        user_id=request.user.id,
        file=staged_file,
        mode=request.POST.get("mode", "new"),
        media_type=media_type,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="clz")
    messages.info(
        request,
        "The task to import your CLZ export has been queued.",
    )
    return _integration_redirect(request, connected_slug="clz")


@require_POST
def import_trakt_export_file(request):
    """View for importing a Trakt data export: a .zip, loose .json files, or a .csv.

    Trakt now exports a .zip of flat .json files, but the older community CSV
    format is still accepted. Loose .json uploads are repackaged into a
    staged zip so the Celery task always receives a single path.
    """
    uploads = request.FILES.getlist("trakt_export") or request.FILES.getlist(
        "trakt_collection_csv",
    )

    if not uploads:
        messages.error(request, "A Trakt export file is required.")
        return _integration_redirect(request)

    staged_files = _stage_uploads_or_message(request, uploads, "Trakt export")
    if staged_files is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    payloads = [
        (upload.name, path)
        for upload, path in zip(uploads, staged_files, strict=True)
    ]

    if len(payloads) == 1 and not _is_trakt_export_payload(*payloads[0]):
        if _queue_staged_task_or_message(
            request,
            tasks.import_trakt_collection_csv,
            user_id=request.user.id,
            file=payloads[0][1],
            mode=mode,
            staged_paths=tuple(staged_files),
        ) is False:
            return _integration_redirect(request, connected_slug="trakt")
        messages.info(
            request,
            "The task to import collection data from the Trakt CSV file has been "
            "queued.",
        )
        return _integration_redirect(request, connected_slug="trakt")

    if len(payloads) == 1 and staged_payload_is_zip(payloads[0][1]):
        archive_path = payloads[0][1]
    else:
        try:
            archive_path = str(build_staged_zip(payloads))
        except OSError:
            for path in staged_files:
                discard_staged_upload(path)
            logger.exception("Could not build staged Trakt export archive")
            messages.error(
                request,
                "The Trakt export could not be prepared. Check available disk space and try again.",
            )
            return _integration_redirect(request)
        for path in staged_files:
            discard_staged_upload(path)

    if _queue_staged_task_or_message(
        request,
        tasks.import_trakt_export,
        user_id=request.user.id,
        file=archive_path,
        mode=mode,
        staged_paths=(archive_path,),
    ) is False:
        return _integration_redirect(request, connected_slug="trakt")
    messages.info(
        request,
        "The task to import your Trakt data export has been queued.",
    )
    return _integration_redirect(request, connected_slug="trakt")


def _is_trakt_export_payload(name, path):
    """Whether an upload is part of the JSON/zip export rather than the legacy CSV."""
    return name.lower().endswith((".zip", ".json")) or staged_payload_is_zip(path)


@app_helpers.answers_json
@require_POST
def import_hltb(request):
    """View for importing game date from HowLongToBeat."""
    file = request.FILES.get("hltb_csv")

    if not file:
        messages.error(request, "HowLongToBeat CSV file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "HowLongToBeat CSV")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_hltb,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="hltb")
    messages.info(
        request,
        "The task to import media from HowLongToBeat CSV file has been queued.",
    )
    return _integration_redirect(request, connected_slug="hltb")


@app_helpers.answers_json
@require_POST
def import_grouvee(request):
    """View for importing game data from a Grouvee export (JSON or zip)."""
    file = request.FILES.get("grouvee_json")

    if not file:
        messages.error(request, "A Grouvee export file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "Grouvee export")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_grouvee,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="grouvee")
    messages.info(
        request,
        "The task to import media from the Grouvee export has been queued.",
    )
    return _integration_redirect(request, connected_slug="grouvee")


@require_POST
def import_steam(request):
    """View for importing game data from Steam."""
    steam_id = request.POST.get("user")
    if not steam_id:
        messages.error(request, "Steam ID is required.")
        return _integration_redirect(request)

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        tasks.import_steam.delay(username=steam_id, user_id=request.user.id, mode=mode)
        messages.info(request, "The task to import media from Steam has been queued.")
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            steam_id,
            request,
            mode,
            frequency,
            import_time,
            "Steam",
        )
    return _integration_redirect(request, connected_slug="steam")


def _arr_connect_view(request, label, connect):
    try:
        connect(
            request.user,
            request.POST.get("base_url", ""),
            request.POST.get("api_key", ""),
            request.POST.get("name", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    messages.success(
        request,
        f"Connected {label}. Initial import queued and recurring sync enabled.",
    )
    return _integration_redirect(request, connected_slug=label.lower())


def _arr_instance_action(request, action):
    """Run a Radarr/Sonarr instance action, mapping a foreign instance to a 404."""
    try:
        return action(request.user, request.POST.get("instance_id"))
    except connections.NotConnectedError as exc:
        raise Http404 from exc


@require_POST
def radarr_connect(request):
    """Connect a new Radarr instance using base URL + API key."""
    return _arr_connect_view(request, "Radarr", connections.connect_radarr)


@require_POST
def radarr_disconnect(request):
    """Disconnect one Radarr instance."""
    _arr_instance_action(request, connections.disconnect_radarr)
    messages.info(request, "Disconnected Radarr.")
    return redirect("import_data")


@require_POST
def import_radarr(request):
    """Queue Radarr import and ensure recurring schedule exists."""
    _arr_instance_action(request, connections.start_radarr_import)
    messages.info(request, "Radarr import queued.")
    return redirect("import_data")


@require_POST
def sonarr_connect(request):
    """Connect a new Sonarr instance using base URL + API key."""
    return _arr_connect_view(request, "Sonarr", connections.connect_sonarr)


@require_POST
def sonarr_disconnect(request):
    """Disconnect one Sonarr instance."""
    _arr_instance_action(request, connections.disconnect_sonarr)
    messages.info(request, "Disconnected Sonarr.")
    return redirect("import_data")


@require_POST
def import_sonarr(request):
    """Queue Sonarr import and ensure recurring schedule exists."""
    _arr_instance_action(request, connections.start_sonarr_import)
    messages.info(request, "Sonarr import queued.")
    return redirect("import_data")


@app_helpers.answers_json
@require_POST
def jellyfin_connect(request):
    """Connect a Jellyfin server using base URL + API key."""
    try:
        connections.connect_jellyfin(
            request.user,
            request.POST.get("base_url", ""),
            request.POST.get("api_key", ""),
            request.POST.get("username", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("integrations")

    messages.success(
        request,
        "Connected Jellyfin. Importing your watch history now.",
    )
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def jellyfin_disconnect(request):
    """Disconnect the Jellyfin integration."""
    connections.disconnect_jellyfin(request.user)
    messages.info(request, "Disconnected Jellyfin.")
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def jellyfin_settings(request):
    """Update Jellyfin push-sync and history-pull toggles."""
    try:
        connections.update_jellyfin_settings(
            request.user,
            push_watched_enabled="push_watched_enabled" in request.POST,
            push_unwatched_enabled="push_unwatched_enabled" in request.POST,
            scheduled_push_enabled="scheduled_push_enabled" in request.POST,
            instant_push_enabled="instant_push_enabled" in request.POST,
            pull_history_enabled="pull_history_enabled" in request.POST,
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("integrations")

    messages.success(request, "Jellyfin sync settings updated.")
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def jellyfin_push_now(request):
    """Queue an immediate Jellyfin watched-state push."""
    try:
        connections.push_jellyfin_now(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("integrations")

    messages.info(request, "Jellyfin sync queued.")
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def jellyfin_pull_now(request):
    """Queue an immediate automatic Jellyfin history pull."""
    try:
        connections.pull_jellyfin_now(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("integrations")

    messages.info(request, "Jellyfin history import queued.")
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def jellyfin_playback_reporting_import(request):
    """Queue a manual Playback Reporting TSV import for the connected user."""
    account = getattr(request.user, "jellyfin_account", None)
    if not account or not account.is_connected:
        messages.error(request, "Connect Jellyfin before importing Playback Reporting data.")
        return redirect("integrations")

    uploaded_file = request.FILES.get("playback_reporting_file")
    if not uploaded_file:
        messages.error(request, "Choose a Playback Reporting TSV export first.")
        return redirect("integrations")

    if uploaded_file.size > JELLYFIN_PLAYBACK_REPORTING_MAX_UPLOAD_BYTES:
        messages.error(request, "The Playback Reporting export is larger than 50 MB.")
        return redirect("integrations")

    if uploaded_file.size == 0:
        messages.error(request, "The Playback Reporting export is empty.")
        return redirect("integrations")

    staged_file = _stage_upload_or_message(
        request,
        uploaded_file,
        "Jellyfin Playback Reporting export",
    )
    if staged_file is None:
        return redirect("integrations")

    if _queue_staged_task_or_message(
        request,
        tasks.import_jellyfin_playback_reporting,
        staged_file,
        request.user.id,
        "new",
        staged_paths=(staged_file,),
    ) is False:
        return redirect("integrations")
    messages.info(request, "Jellyfin Playback Reporting import queued.")
    return redirect("integrations")


@require_POST
def audiobookshelf_connect(request):
    """Connect Audiobookshelf account using base URL + API token."""
    try:
        connections.connect_audiobookshelf(
            request.user,
            request.POST.get("base_url", ""),
            request.POST.get("api_token", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    messages.success(request, "Connected Audiobookshelf. Initial import queued.")
    return _integration_redirect(request, connected_slug="audiobookshelf")


@require_POST
def audiobookshelf_disconnect(request):
    """Disconnect Audiobookshelf integration."""
    connections.disconnect_audiobookshelf(request.user)
    messages.info(request, "Disconnected Audiobookshelf.")
    return redirect("import_data")


@require_POST
def import_audiobookshelf(request):
    """Queue Audiobookshelf import and ensure recurring schedule exists."""
    try:
        connections.start_audiobookshelf_import(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Audiobookshelf import queued.")
    return redirect("import_data")


AUDIOBOOKSHELF_COVER_TIMEOUT = 15
# Plain raster types only - an upstream ABS server (attacker-controlled, or
# just compromised) returning e.g. text/html or image/svg+xml would have it
# served as active content from Floppy's own origin to anyone holding the
# signed proxy URL, since the account owner can share that URL freely.
# The non-standard spellings are here because real ABS deployments behind a
# reverse proxy do emit them, and rejecting one lost the poster (#861).
AUDIOBOOKSHELF_COVER_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/pjpeg",
        "image/png",
        "image/x-png",
        "image/webp",
        "image/gif",
        "image/avif",
        "image/bmp",
        "image/tiff",
        "image/heic",
        "image/heif",
    },
)
# Content types that mean "I don't know", where sniffing the body is the only
# way to tell a real cover from something we must not serve.
AUDIOBOOKSHELF_COVER_UNTYPED = frozenset({"", "application/octet-stream"})
# Leading magic bytes for the raster formats above. WebP is RIFF....WEBP, so it
# is matched on two separate offsets rather than a single prefix.
COVER_MAGIC_PREFIXES = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
)
COVER_SNIFF_BYTES = 16


def _sniff_cover_content_type(body: bytes) -> str:
    """Return the image type of `body` from its magic bytes, or "" if unknown.

    Deliberately recognises raster formats only: an SVG or HTML body has no
    magic number here and so stays rejected, exactly as an explicit
    image/svg+xml content type would be.
    """
    for prefix, content_type in COVER_MAGIC_PREFIXES:
        if body.startswith(prefix):
            return content_type
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if body[4:8] == b"ftyp":
        brand = body[8:12]
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        if brand in {b"heic", b"heix", b"heim", b"heis", b"mif1", b"msf1"}:
            return "image/heic"
    return ""


def _placeholder_image_bytes():
    """Decode settings.IMG_NONE into (body, content_type), or None.

    IMG_NONE is a base64 data URI by default but is overridable to a plain URL,
    which there is nothing to decode from. Decoded per call rather than cached
    so an overridden setting is always honoured; this only runs on the failure
    path, where one small base64 decode is not worth a staleness hazard.
    """
    prefix = "data:"
    value = settings.IMG_NONE or ""
    if not value.startswith(prefix):
        return None
    header, _, payload = value[len(prefix) :].partition(",")
    if not payload:
        return None
    content_type, _, encoding = header.partition(";")
    if encoding.strip().lower() != "base64":
        return None
    try:
        return base64.b64decode(payload), content_type.strip() or "image/svg+xml"
    except (binascii.Error, ValueError):
        return None


def _placeholder_image_response():
    """Return Floppy's own "no artwork" placeholder as a real image response.

    A 404 here renders as the browser's broken-image glyph, because nothing in
    the templates has an onerror fallback and the stored URL is a perfectly
    valid proxy URL (#861). Serving the placeholder instead keeps the grid
    looking the way it does for any other artless item. The bytes are Floppy's
    own fixed SVG, never anything the upstream server influenced, and the TTL
    is short so the real cover reappears once ABS recovers.
    """
    decoded = _placeholder_image_bytes()
    if decoded is None:
        return HttpResponseNotFound()
    body, content_type = decoded
    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_not_required
@require_GET
def audiobookshelf_cover(request, token):
    """Stream an Audiobookshelf item's cover art using the account's own token.

    The ABS `/api/items/:id/cover` endpoint requires a bearer token, so it
    can't be embedded directly in an `<img src>`. This resolves the signed
    token to the owning account, fetches the cover server-side with that
    account's stored credentials, and streams it back (see #861). The
    endpoint is deliberately anonymous, so the response is streamed with a
    hard size cap and its content type is restricted to known-safe image
    types - matching the bounded, allow-listed fetch app.image_cache already
    does for provider artwork.

    Every failure below is logged and answered with Floppy's own placeholder
    rather than a bare 404: the 404s were both invisible in Settings > Advanced
    and rendered as broken-image glyphs, which is what made #861 impossible to
    diagnose from a bug report.
    """
    resolved = abs_cover_proxy.resolve_cover_proxy_token(token)
    if resolved is None:
        # A tampered or malformed token is not something a Floppy page can
        # produce, so this one stays a plain 404. It is logged at debug
        # rather than warning because the view is anonymous: anyone could
        # otherwise flood the log with junk tokens and bury the real
        # Audiobookshelf failures below, which are the point of #861. Every
        # other branch here needs a valid signature to reach.
        logger.debug("Audiobookshelf cover proxy rejected an unsignable token")
        return HttpResponseNotFound()
    account_id, library_item_id = resolved

    account = AudiobookshelfAccount.objects.filter(pk=account_id).first()
    if account is None:
        logger.warning(
            "Audiobookshelf cover unavailable: no account account=%s item=%s",
            account_id,
            library_item_id,
        )
        return _placeholder_image_response()

    try:
        api_token = helpers.decrypt(account.api_token)
    except Exception as error:
        logger.warning(
            "Audiobookshelf cover unavailable: token decrypt failed "
            "account=%s item=%s error=%s",
            account_id,
            library_item_id,
            exception_summary(error),
        )
        return _placeholder_image_response()

    cover_url = f"{account.base_url.rstrip('/')}/api/items/{library_item_id}/cover"
    try:
        upstream = requests.get(
            cover_url,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=AUDIOBOOKSHELF_COVER_TIMEOUT,
            stream=True,
        )
    except requests.RequestException as error:
        logger.warning(
            "Audiobookshelf cover unavailable: request failed "
            "account=%s item=%s error=%s",
            account_id,
            library_item_id,
            exception_summary(error),
        )
        return _placeholder_image_response()

    try:
        if upstream.status_code != HTTPStatus.OK:
            logger.warning(
                "Audiobookshelf cover unavailable: upstream status=%s "
                "account=%s item=%s",
                upstream.status_code,
                account_id,
                library_item_id,
            )
            return _placeholder_image_response()

        content_type = (
            upstream.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if (
            content_type not in AUDIOBOOKSHELF_COVER_CONTENT_TYPES
            and content_type not in AUDIOBOOKSHELF_COVER_UNTYPED
        ):
            logger.warning(
                "Audiobookshelf cover unavailable: refused content_type=%s "
                "account=%s item=%s",
                content_type,
                account_id,
                library_item_id,
            )
            return _placeholder_image_response()

        try:
            content_length = int(upstream.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > image_cache.MAX_IMAGE_BYTES:
            logger.warning(
                "Audiobookshelf cover unavailable: declared content_length=%s "
                "over cap account=%s item=%s",
                content_length,
                account_id,
                library_item_id,
            )
            return _placeholder_image_response()

        body = bytearray()
        oversized = False
        for chunk in upstream.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > image_cache.MAX_IMAGE_BYTES:
                oversized = True
                break
    finally:
        upstream.close()

    if oversized:
        logger.warning(
            "Audiobookshelf cover unavailable: body exceeded %s bytes "
            "account=%s item=%s",
            image_cache.MAX_IMAGE_BYTES,
            account_id,
            library_item_id,
        )
        return _placeholder_image_response()

    body = bytes(body)
    # An upstream that declares nothing useful still has to prove it sent a
    # raster image; sniffing keeps SVG and HTML out just as the allow-list does.
    if content_type in AUDIOBOOKSHELF_COVER_UNTYPED:
        sniffed = _sniff_cover_content_type(body[:COVER_SNIFF_BYTES])
        if not sniffed:
            logger.warning(
                "Audiobookshelf cover unavailable: untyped body was not an image "
                "content_type=%s account=%s item=%s",
                content_type,
                account_id,
                library_item_id,
            )
            return _placeholder_image_response()
        content_type = sniffed

    response = HttpResponse(body, content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


PLEX_COVER_TIMEOUT = 15
# Same allow-list as the Audiobookshelf proxy: a Plex server is an arbitrary
# user-configured host, so anything but a plain raster type would be served as
# active content from Floppy's own origin to whoever holds the signed URL.
PLEX_COVER_CONTENT_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"},
)


@login_not_required
@require_GET
def plex_cover(request, token):
    """Stream a Plex item's cover art using the account's own Plex token.

    Plex art endpoints require an X-Plex-Token, which must never end up in an
    `<img src>` or in a stored Item.image. This resolves the signed token to the
    owning account and server, fetches the art server-side, and streams it back
    under the same size cap and content-type allow-list as the Audiobookshelf
    cover proxy.
    """
    resolved = plex_cover_proxy.resolve_cover_proxy_token(token)
    if resolved is None:
        return HttpResponseNotFound()
    account_id, machine_identifier, thumb_path = resolved

    account = PlexAccount.objects.filter(pk=account_id).first()
    if account is None:
        return HttpResponseNotFound()

    uri, plex_token = plex_api.connection_for_machine(
        account.sections,
        machine_identifier,
        account.plex_token,
    )
    if not uri or not plex_token:
        return HttpResponseNotFound()

    try:
        upstream = requests.get(
            f"{uri}{thumb_path}",
            params={"X-Plex-Token": plex_token},
            timeout=PLEX_COVER_TIMEOUT,
            stream=True,
            verify=settings.PLEX_SSL_VERIFY,
        )
    except requests.RequestException:
        return HttpResponseNotFound()

    try:
        if upstream.status_code != HTTPStatus.OK:
            return HttpResponseNotFound()

        content_type = (
            upstream.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if content_type not in PLEX_COVER_CONTENT_TYPES:
            return HttpResponseNotFound()

        try:
            content_length = int(upstream.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length > image_cache.MAX_IMAGE_BYTES:
            return HttpResponseNotFound()

        body = bytearray()
        for chunk in upstream.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            body.extend(chunk)
            if len(body) > image_cache.MAX_IMAGE_BYTES:
                return HttpResponseNotFound()
    finally:
        upstream.close()

    response = HttpResponse(bytes(body), content_type=content_type)
    response["Cache-Control"] = "private, max-age=3600"
    return response


STORYTELLER_PENDING_SESSION_KEY = "storyteller_pending_auth"


def _fix_storyteller_uri(uri, base_url):
    """Rewrite a verification URI's host to the configured server URL.

    Storyteller may return verification URLs with an internal host/port
    (e.g. 0.0.0.0:80); keep only the path and re-root it on the server URL.
    """
    if not uri:
        return uri
    match = re.match(r"^https?://[^/]+(/.*)$", uri) or re.match(r"^(/.*)$", uri)
    if match:
        return base_url + match.group(1)
    return uri


@require_POST
def storyteller_connect(request):
    """Begin the Storyteller device-code login flow."""
    server_url = request.POST.get("server_url", "").strip().rstrip("/")
    if not server_url:
        messages.error(request, "Storyteller server URL is required.")
        return _integration_redirect(request)

    try:
        data = StorytellerClient(server_url).start_device_auth()
    except StorytellerClientError as exc:
        messages.error(request, str(exc))
        return _integration_redirect(request)
    except Exception as exc:
        messages.error(request, f"Failed to reach Storyteller: {exc}")
        return _integration_redirect(request)

    device_code = data.get("device_code")
    if not device_code:
        messages.error(request, "Storyteller did not return a device code.")
        return _integration_redirect(request)

    expires_in = int(data.get("expires_in") or 600)
    request.session[STORYTELLER_PENDING_SESSION_KEY] = {
        "server_url": server_url,
        "device_code": device_code,
        "user_code": data.get("user_code") or "",
        "verification_uri": _fix_storyteller_uri(
            data.get("verification_uri"), server_url
        ),
        "verification_uri_complete": _fix_storyteller_uri(
            data.get("verification_uri_complete"),
            server_url,
        ),
        "interval": int(data.get("interval") or 5),
        "expires_at": (timezone.now() + timedelta(seconds=expires_in)).isoformat(),
    }
    request.session.modified = True
    messages.info(
        request, "Approve the login on your Storyteller server to finish connecting."
    )
    return redirect("import_data")


@require_GET
def storyteller_poll(request):
    """Poll Storyteller for the access token during device login."""
    pending = request.session.get(STORYTELLER_PENDING_SESSION_KEY)
    if not pending:
        return JsonResponse({"status": "idle"})

    expires_at = pending.get("expires_at")
    if expires_at and timezone.now() > datetime.fromisoformat(expires_at):
        request.session.pop(STORYTELLER_PENDING_SESSION_KEY, None)
        return JsonResponse({"status": "expired"})

    client = StorytellerClient(pending["server_url"])
    try:
        data, status_code = client.poll_device_token(pending["device_code"])
    except Exception as exc:
        return JsonResponse({"status": "pending", "detail": str(exc)})

    access_token = data.get("access_token") if isinstance(data, dict) else None
    if access_token:

        def _connect():
            StorytellerAccount.objects.update_or_create(
                user=request.user,
                defaults={
                    "server_url": pending["server_url"],
                    "auth_token": helpers.encrypt(access_token),
                    "connection_broken": False,
                    "last_error_message": "",
                },
            )
            _ensure_storyteller_schedule(request.user)

        _run_with_lock_retry("connect Storyteller", _connect)
        request.session.pop(STORYTELLER_PENDING_SESSION_KEY, None)
        tasks.import_storyteller.delay(user_id=request.user.id, mode="new")
        return JsonResponse({"status": "connected"})

    error = data.get("error") if isinstance(data, dict) else None
    if (
        error in ("authorization_pending", "slow_down")
        or status_code == HTTPStatus.BAD_REQUEST
    ):
        return JsonResponse({"status": "pending"})

    request.session.pop(STORYTELLER_PENDING_SESSION_KEY, None)
    return JsonResponse({"status": "error", "message": error or "Login failed."})


@require_POST
def storyteller_cancel(request):
    """Cancel an in-progress Storyteller device login."""
    request.session.pop(STORYTELLER_PENDING_SESSION_KEY, None)
    messages.info(request, "Storyteller login cancelled.")
    return redirect("import_data")


@require_POST
def storyteller_disconnect(request):
    """Disconnect the Storyteller integration."""
    connections.disconnect_storyteller(request.user)
    messages.info(request, "Disconnected Storyteller.")
    return redirect("import_data")


@require_POST
def import_storyteller(request):
    """Queue a Storyteller import and ensure the recurring schedule exists."""
    try:
        connections.start_storyteller_import(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Storyteller import queued.")
    return redirect("import_data")


def _koreader_form_options(post):
    """Read KOReader account toggles from a form POST."""
    return {
        "verify_ssl": post.get("verify_ssl") == "on",
        "create_missing": post.get("create_missing") == "on",
        "skip_finished_books": post.get("skip_finished_books") == "on",
        "finished_threshold_percent": post.get("finished_threshold_percent") or "",
    }


@require_POST
def koreader_connect(request):
    """Connect a KOReader sync server account."""
    mode = request.POST.get("mode", "new")
    frequency = request.POST.get("frequency", "once")
    import_time = request.POST.get("time", "00:00")

    try:
        account = connections.connect_koreader(
            request.user,
            request.POST.get("server_url", ""),
            request.POST.get("username", ""),
            request.POST.get("password", ""),
            **_koreader_form_options(request.POST),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    if frequency == "once":
        connections.queue_koreader_import(request.user, mode)
        messages.success(request, "Connected to KOReader. Import queued.")
    else:
        helpers.create_import_schedule(
            username=account.username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="KOReader",
            extra_kwargs={"user_id": request.user.id},
        )
        connections.queue_koreader_import(request.user, mode)
        messages.success(request, "Connected to KOReader. Import scheduled.")
    return redirect("import_data")


@require_POST
def koreader_settings(request):
    """Update KOReader connection and sync options."""
    try:
        connections.update_koreader_settings(
            request.user,
            request.POST.get("server_url", ""),
            request.POST.get("username", ""),
            request.POST.get("password", ""),
            **_koreader_form_options(request.POST),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.success(request, "KOReader settings saved.")
    return redirect("import_data")


@require_POST
def koreader_disconnect(request):
    """Disconnect the KOReader integration."""
    connections.disconnect_koreader(request.user)
    messages.info(request, "Disconnected KOReader.")
    return redirect("import_data")


@require_POST
def import_koreader(request):
    """Queue a KOReader import or update its schedule."""
    account = getattr(request.user, "koreader_account", None)
    if not account:
        messages.error(request, "Connect KOReader before importing.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]
    import_time = request.POST["time"]

    if frequency == "once":
        connections.start_koreader_import(request.user, mode)
        messages.info(request, "KOReader import queued.")
    else:
        helpers.create_import_schedule(
            username=account.username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source="KOReader",
            extra_kwargs={"user_id": request.user.id},
        )
    return redirect("import_data")


@require_POST
def stremio_connect(request):
    """Connect a Stremio account using email/password or a pasted auth key."""
    try:
        connections.connect_stremio(
            request.user,
            request.POST.get("email", ""),
            request.POST.get("password", ""),
            request.POST.get("auth_key", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    messages.success(
        request,
        "Connected to Stremio. Initial import queued; your library will sync every 2 hours.",
    )
    return _integration_redirect(request, connected_slug="stremio")


@require_POST
def stremio_disconnect(request):
    """Disconnect the Stremio integration."""
    connections.disconnect_stremio(request.user)
    messages.info(request, "Disconnected Stremio.")
    return redirect("import_data")


@require_POST
def import_stremio(request):
    """Queue a Stremio import and ensure the recurring schedule exists."""
    try:
        connections.start_stremio_import(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Stremio import queued.")
    return redirect("import_data")


def _console_import_params(request):
    """Read a console import's mode/frequency/time from the form POST."""
    return {
        "mode": request.POST.get("mode") or "new",
        "frequency": request.POST.get("frequency") or "once",
        "time": request.POST.get("time") or connections.CONSOLE_DEFAULT_IMPORT_TIME,
    }


def _report_console_import(request, source, queued):
    """Turn a console import outcome into the message the web UI has always shown."""
    if queued.outcome == "reenabled":
        messages.success(request, f"{source} import task re-enabled.")
    elif queued.outcome == "scheduled":
        messages.success(request, f"{source} import task scheduled.")
    else:
        messages.info(
            request,
            f"The task to import media from {source} has been queued.",
        )


def _schedule_console_import(request, source, task, recurring_task_name):
    """Start a console import right after connecting, with lock retry."""
    params = _console_import_params(request)
    try:
        queued = _run_with_lock_retry(
            f"schedule {source} import",
            lambda: connections.start_console_import(
                request.user, source, task, recurring_task_name, **params
            ),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return
    _report_console_import(request, source, queued)


@require_POST
def xbox_connect(request):
    """Connect an Xbox account using an OpenXBL API key."""
    try:
        account = connections.connect_xbox(request.user, request.POST.get("api_key", ""))
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.success(request, f"Connected to Xbox as {account.gamertag or account.xuid}.")
    _schedule_console_import(
        request, "Xbox", tasks.import_xbox, connections.XBOX_RECURRING_TASK_NAME
    )
    return redirect("import_data")


@require_POST
def xbox_disconnect(request):
    """Disconnect the Xbox integration."""
    connections.disconnect_xbox(request.user)
    messages.info(request, "Disconnected Xbox.")
    return redirect("import_data")


@require_POST
def import_xbox(request):
    """Queue a one-off Xbox import or schedule a recurring one."""
    try:
        queued = connections.start_xbox_import(
            request.user, **_console_import_params(request)
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    _report_console_import(request, "Xbox", queued)
    return redirect("import_data")


@require_POST
def psn_connect(request):
    """Connect a PlayStation Network account using an NPSSO token."""
    try:
        account = connections.connect_psn(request.user, request.POST.get("npsso", ""))
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.success(
        request,
        f"Connected to PlayStation Network as {account.online_id or account.account_id}.",
    )
    _schedule_console_import(
        request, "PSN", tasks.import_psn, connections.PSN_RECURRING_TASK_NAME
    )
    return redirect("import_data")


@require_POST
def psn_disconnect(request):
    """Disconnect the PlayStation Network integration."""
    connections.disconnect_psn(request.user)
    messages.info(request, "Disconnected PlayStation Network.")
    return redirect("import_data")


@require_POST
def import_psn(request):
    """Queue a one-off PSN import or schedule a recurring one."""
    try:
        queued = connections.start_psn_import(
            request.user, **_console_import_params(request)
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    _report_console_import(request, "PSN", queued)
    return redirect("import_data")


@require_POST
def pocketcasts_connect(request):
    """Connect Pocket Casts account using email and password."""
    try:
        account = connections.connect_pocketcasts(
            request.user,
            request.POST.get("email", ""),
            request.POST.get("password", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    if account.initial_import_queued:
        messages.success(
            request,
            "Connected to Pocket Casts successfully. Initial import queued. Recurring imports will run every 2 hours.",
        )
    else:
        messages.success(request, "Connected to Pocket Casts successfully.")
    return _integration_redirect(request, connected_slug="pocketcasts")


@require_POST
def pocketcasts_disconnect(request):
    """Remove stored Pocket Casts credentials and delete periodic import task."""
    connections.disconnect_pocketcasts(request.user)
    messages.info(request, "Disconnected Pocket Casts and removed scheduled imports.")
    return redirect("import_data")


@require_POST
def gpodder_connect(request):
    """Connect a GPodder-compatible account using Basic Auth credentials."""
    try:
        account = connections.connect_gpodder(
            request.user,
            request.POST.get("server_url", ""),
            request.POST.get("username", ""),
            request.POST.get("password", ""),
            request.POST.get("device_filter", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    if account.initial_import_queued:
        messages.success(
            request,
            "Connected to GPodder successfully. Initial sync queued. Recurring syncs will run every 2 hours.",
        )
    else:
        messages.success(request, "Connected to GPodder successfully.")
    return _integration_redirect(request, connected_slug="gpodder")


@require_POST
def gpodder_disconnect(request):
    """Remove stored GPodder credentials and scheduled imports."""
    connections.disconnect_gpodder(request.user)
    messages.info(request, "Disconnected GPodder and removed scheduled imports.")
    return redirect("import_data")


@require_POST
def lastfm_connect(request):
    """Connect Last.fm account using username."""
    try:
        connections.connect_lastfm(request.user, request.POST.get("lastfm_username", ""))
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    poll_interval_minutes = getattr(settings, "LASTFM_POLL_INTERVAL_MINUTES", 15)
    messages.success(
        request,
        (
            "Connected to Last.fm successfully. Recurring syncs will run every "
            f"{poll_interval_minutes} minutes. Initial sync and full history import queued."
        ),
    )
    return _integration_redirect(request, connected_slug="lastfm")


@require_POST
def lastfm_disconnect(request):
    """Remove Last.fm connection."""
    connections.disconnect_lastfm(request.user)
    messages.info(request, "Disconnected Last.fm.")
    return redirect("import_data")


@require_POST
def poll_lastfm_manual(request):
    """Manually trigger Last.fm polling for the current user."""
    try:
        connections.poll_lastfm_now(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Last.fm sync queued. Scrobbles will be imported shortly.")
    return redirect("import_data")


@require_POST
def import_lastfm_history_manual(request):
    """Queue or rerun a full Last.fm history import for the current user."""
    try:
        connections.start_lastfm_history_import(request.user)
    except connections.AlreadyRunningError as exc:
        messages.info(request, exc.web_message)
        return redirect("import_data")
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Full Last.fm history import queued.")
    return redirect("import_data")


@require_POST
def koito_connect(request):
    """Connect a Koito account using base URL + API key."""
    try:
        connections.connect_koito(
            request.user,
            request.POST.get("base_url", ""),
            request.POST.get("api_key", ""),
        )
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return _integration_redirect(request)

    messages.success(request, "Connected Koito. Full history import queued.")
    return _integration_redirect(request, connected_slug="koito")


@require_POST
def koito_disconnect(request):
    """Disconnect the Koito integration."""
    connections.disconnect_koito(request.user)
    messages.info(request, "Disconnected Koito.")
    return redirect("import_data")


@require_POST
def poll_koito_manual(request):
    """Manually trigger a Koito sync for the current user."""
    try:
        connections.poll_koito_now(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Koito sync queued. Listens will be imported shortly.")
    return redirect("import_data")


@require_POST
def import_koito_history_manual(request):
    """Queue or rerun a full Koito history import for the current user."""
    try:
        connections.start_koito_history_import(request.user)
    except connections.AlreadyRunningError as exc:
        messages.info(request, exc.web_message)
        return redirect("import_data")
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    messages.info(request, "Full Koito history import queued.")
    return redirect("import_data")


@require_POST
def import_pocketcasts(request):
    """Queue a Pocket Casts history import for the current user.

    Pocket Casts always uses mode="new" and runs every 2 hours automatically.
    """
    try:
        queued = connections.start_pocketcasts_import(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    if queued.schedule_created:
        messages.info(
            request,
            "The task to import media from Pocket Casts has been queued. Recurring imports will run every 2 hours.",
        )
    else:
        messages.info(
            request, "The task to import media from Pocket Casts has been queued."
        )
    return redirect("import_data")


@require_POST
def import_gpodder(request):
    """Queue a GPodder podcast history sync for the current user."""
    try:
        queued = connections.start_gpodder_import(request.user)
    except connections.IntegrationError as exc:
        messages.error(request, exc.web_message)
        return redirect("import_data")

    if queued.schedule_created:
        messages.info(
            request,
            "The task to import media from GPodder has been queued. Recurring syncs will run every 2 hours.",
        )
    else:
        messages.info(request, "The task to import media from GPodder has been queued.")
    return redirect("import_data")


@app_helpers.answers_json
def import_imdb(request):
    """View for importing data from IMDB."""
    file = request.FILES.get("imdb_csv")

    if not file:
        messages.error(request, "IMDB CSV file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "IMDB CSV")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_imdb,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="imdb")
    messages.info(
        request,
        "The task to import media from IMDB CSV file has been queued.",
    )
    return _integration_redirect(request, connected_slug="imdb")


@app_helpers.answers_json
@require_POST
def import_goodreads(request):
    """View for importing books data from Goodreads CSV."""
    file = request.FILES.get("goodreads_csv")

    if not file:
        messages.error(request, "Goodreads CSV file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "Goodreads CSV")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_goodreads,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="goodreads")
    messages.info(
        request,
        "The task to import media from Goodreads CSV file has been queued.",
    )
    return _integration_redirect(request, connected_slug="goodreads")


@app_helpers.answers_json
@require_POST
def import_hardcover(request):
    """View for importing books data from Hardcover CSV and/or saving a personal API key."""
    file = request.FILES.get("hardcover_csv")
    api_key = request.POST.get("hardcover_api_key", "").strip()

    if not file and not api_key:
        messages.error(request, "Enter a Hardcover API key or select a CSV file.")
        return _integration_redirect(request)

    if api_key:
        credentials.set_user("hardcover", request.user, {"api_key": api_key})
        messages.success(request, "Hardcover API key saved.")

    if file:
        staged_file = _stage_upload_or_message(request, file, "Hardcover CSV")
        if staged_file is None:
            return _integration_redirect(request, connected_slug="hardcover")

        mode = request.POST["mode"]
        if _queue_staged_task_or_message(
            request,
            tasks.import_hardcover,
            user_id=request.user.id,
            file=staged_file,
            mode=mode,
            staged_paths=(staged_file,),
        ) is False:
            return _integration_redirect(request, connected_slug="hardcover")
        messages.info(
            request,
            "The task to import media from Hardcover CSV file has been queued.",
        )

    return _integration_redirect(request, connected_slug="hardcover")


@app_helpers.answers_json
@require_POST
def import_storygraph(request):
    """View for importing books data from StoryGraph CSV."""
    file = request.FILES.get("storygraph_csv")

    if not file:
        messages.error(request, "StoryGraph CSV file is required.")
        return _integration_redirect(request)

    staged_file = _stage_upload_or_message(request, file, "StoryGraph CSV")
    if staged_file is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    if _queue_staged_task_or_message(
        request,
        tasks.import_storygraph,
        user_id=request.user.id,
        file=staged_file,
        mode=mode,
        staged_paths=(staged_file,),
    ) is False:
        return _integration_redirect(request, connected_slug="storygraph")
    messages.info(
        request,
        "The task to import media from StoryGraph CSV file has been queued.",
    )
    return _integration_redirect(request, connected_slug="storygraph")


@app_helpers.answers_json
@require_POST
def import_tvtime(request):
    """View for importing watch history from TV Time's GDPR export CSVs."""
    shows_file = request.FILES.get("tvtime_shows_csv")
    movies_file = request.FILES.get("tvtime_movies_csv")

    if not shows_file and not movies_file:
        messages.error(
            request,
            "Select at least one TV Time CSV file (shows and/or movies).",
        )
        return _integration_redirect(request)

    uploads = [upload for upload in (shows_file, movies_file) if upload]
    staged_files = _stage_uploads_or_message(request, uploads, "TV Time CSV")
    if staged_files is None:
        return _integration_redirect(request)

    mode = request.POST["mode"]
    staged_index = 0
    if shows_file:
        staged_file = staged_files[staged_index]
        staged_index += 1
        if _queue_staged_task_or_message(
            request,
            tasks.import_tvtime_shows,
            user_id=request.user.id,
            file=staged_file,
            mode=mode,
            staged_paths=(staged_file,),
        ) is False:
            for path in staged_files[staged_index:]:
                discard_staged_upload(path)
            return _integration_redirect(request, connected_slug="tvtime")
    if movies_file:
        staged_file = staged_files[staged_index]
        if _queue_staged_task_or_message(
            request,
            tasks.import_tvtime_movies,
            user_id=request.user.id,
            file=staged_file,
            mode=mode,
            staged_paths=(staged_file,),
        ) is False:
            return _integration_redirect(request, connected_slug="tvtime")
    messages.info(
        request,
        "The task to import media from TV Time CSV file(s) has been queued.",
    )
    return _integration_redirect(request, connected_slug="tvtime")


@require_GET
def import_template_csv(request):
    """View for downloading a sample CSV demonstrating the import format."""
    content = exports.generate_sample_template()
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = (
        'attachment; filename="floppy_import_template.csv"'
    )
    return response


@require_GET
def export_csv(request):
    """View for exporting all media data to a CSV file."""
    selected_media_types = request.GET.getlist("media_types")
    include_lists = request.GET.get("include_lists", "on") == "on"
    include_collection = request.GET.get("include_collection", "on") == "on"

    if selected_media_types:
        media_types = selected_media_types
    elif request.GET:
        # explicit request with no media types checked -> lists/collection-only
        # when either is included
        media_types = [] if include_lists or include_collection else None
    else:
        media_types = None

    now = timezone.localtime()
    response = StreamingHttpResponse(
        streaming_content=exports.generate_rows(
            request.user,
            media_types=media_types,
            include_lists=include_lists,
            include_collection=include_collection,
        ),
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="floppy_{now}.csv"'},
    )
    logger.info("User %s started CSV export", request.user.username)
    return response


@require_GET
def export_csv_letterboxd(request):
    """View for exporting the user's watched movies as a Letterboxd import CSV."""
    now = timezone.localtime()
    response = StreamingHttpResponse(
        streaming_content=exports.generate_letterboxd_rows(request.user),
        content_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="letterboxd_{now}.csv"',
        },
    )
    logger.info("User %s started Letterboxd CSV export", request.user.username)
    return response


@login_not_required
@csrf_exempt
@require_POST
def jellyfin_webhook(request, token):
    """Handle Jellyfin webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Jellyfin webhook: Invalid token",
        )
        return HttpResponse(status=401)

    data = request.body
    if not data:
        logger.warning("Missing payload in Jellyfin webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("Invalid JSON", status=400)
    if not isinstance(payload, dict):
        return HttpResponse("Invalid payload", status=400)
    if not _queue_task_quietly(tasks.process_webhook, "jellyfin", payload, user.id):
        return HttpResponse(status=503)
    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def plex_webhook(request, token):
    """Handle Plex webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Plex webhook: Invalid token",
        )
        return HttpResponse(status=401)

    # https://support.plex.tv/hc/en-us/articles/115002267687-Webhooks
    # As stated above, the payload is sent in JSON format inside a multipart
    # HTTP POST request. For the media.play and media.rate events, a second part of
    # the POST request contains a JPEG thumbnail for the media.

    data = request.POST.get("payload")
    if not data:
        logger.warning("Missing payload in Plex webhook request")
        user.mark_plex_webhook_error("Missing payload in Plex webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload in Plex webhook request")
        user.mark_plex_webhook_error("Invalid JSON payload in Plex webhook request")
        return HttpResponse("Invalid payload", status=400)

    event_type = payload.get("event")
    logger.info(
        "Received Plex webhook request - Event: %s, User: %s", event_type, user.username
    )

    tasks.process_webhook.delay("plex", payload, user.id)
    payload_usernames = extract_plex_webhook_usernames(payload)
    for share in PlexWebhookShare.objects.filter(
        owner=user,
        recipient_enabled=True,
        recipient__is_active=True,
    ).only("id", "recipient_id", "plex_username"):
        if share.plex_username.strip().casefold() in payload_usernames:
            tasks.process_webhook.delay(
                "plex",
                payload,
                share.recipient_id,
                share_id=share.id,
            )
    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def emby_webhook(request, token):
    """Handle Emby webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Emby webhook: Invalid token",
        )
        return HttpResponse(status=401)

    # The payload is sent in JSON format inside a multipart
    # HTTP POST request.

    data = request.POST.get("data")
    if not data:
        logger.warning("Missing payload in Emby webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse("Invalid JSON", status=400)
    if not isinstance(payload, dict):
        return HttpResponse("Invalid payload", status=400)
    if not _queue_task_quietly(tasks.process_webhook, "emby", payload, user.id):
        return HttpResponse(status=503)
    return HttpResponse(status=200)


# kept: URL name — renaming breaks already-configured Seerr/Jellyseerr webhook URLs
@login_not_required
@csrf_exempt
@require_POST
def jellyseerr_webhook(request, token):
    """Handle Seerr webhook notifications for requested/approved media."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Seerr webhook: Invalid token",
        )
        return HttpResponse(status=401)

    data = request.body
    if not data:
        logger.warning("Missing payload in Seerr webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except Exception:
        logger.warning("Invalid JSON payload in Seerr webhook request")
        return HttpResponse("Invalid JSON", status=400)

    tasks.process_webhook.delay("seerr", payload, user.id)
    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def seerr_global_webhook(request):
    """Handle a single shared Seerr webhook for multiple Floppy users.

    Unlike the per-user Seerr webhook, this endpoint has no per-user
    token in the URL, so it demultiplexes users by matching the payload's
    requester username against each opted-in user's allowed usernames.
    """
    if not settings.SEERR_GLOBAL_WEBHOOK_SECRET:
        return HttpResponse(status=404)

    data = request.body
    if not data:
        logger.warning("Missing payload in Seerr global webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except Exception:
        logger.warning("Invalid JSON payload in Seerr global webhook request")
        return HttpResponse("Invalid JSON", status=400)

    if not hmac.compare_digest(
        str(payload.get("secret", "")),
        settings.SEERR_GLOBAL_WEBHOOK_SECRET,
    ):
        logger.warning("Seerr global webhook: invalid or missing secret")
        return HttpResponse(status=401)

    requester = (payload.get("requestedBy_username") or "").strip() or (
        payload.get("notifyuser_username") or ""
    ).strip()
    if not requester:
        logger.warning("Missing requester in Seerr global webhook request")
        return HttpResponse("Missing requester", status=400)

    matched = False
    for user in users.models.User.objects.filter(
        jellyseerr_enabled=True,
        is_active=True,
    ).exclude(jellyseerr_allowed_usernames=""):
        allowed = {
            username.strip().lower()
            for username in user.jellyseerr_allowed_usernames.split(",")
            if username.strip()
        }
        if requester.lower() in allowed:
            matched = True
            tasks.process_webhook.delay("seerr", payload, user.id)

    if not matched:
        logger.info(
            "Seerr global webhook: no user matched requester=%r",
            requester,
        )

    return HttpResponse(status=200)


@login_not_required
@csrf_exempt
@require_POST
def kodi_webhook(request, token):
    """Handle Kodi webhook notifications for media playback."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Kodi webhook: Invalid token",
        )
        return HttpResponse(status=401)

    data = request.body
    if not data:
        logger.warning("Missing payload in Kodi webhook request")
        return HttpResponse("Missing payload", status=400)

    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        logger.warning("Invalid JSON payload in Kodi webhook request")
        return HttpResponse("Invalid JSON", status=400)

    tasks.process_webhook.delay("kodi", payload, user.id)
    return HttpResponse(status=200)


STREMIO_ADDON_MANIFEST = {
    # Keep the existing addon id so installed clients remain compatible.
    "id": "org.yamtrack.scrobbler",
    "version": "1.2.0",
    "name": "Floppy",
    "description": (
        "Floppy Watchlist catalogs and playback scrobbling for Stremio."
    ),
    "resources": ["catalog", "meta", "subtitles"],
    "types": ["movie", "series"],
    "idPrefixes": ["tt"],
    "catalogs": [],
    "behaviorHints": {"configurable": True, "configurationRequired": False},
}
STREMIO_SCROBBLE_THROTTLE_SECONDS = 1800
STREMIO_MAX_MEDIA_ID_LENGTH = 128
STREMIO_MEDIA_ID_PATTERN = re.compile(
    r"^tt[0-9]+(?::[1-9][0-9]*:[1-9][0-9]*)?$",
)


def _stremio_addon_response(payload, status=200):
    """Build a JSON response with the CORS headers Stremio requires."""
    response = JsonResponse(payload, status=status)
    response["Access-Control-Allow-Origin"] = "*"
    return response


@login_not_required
@csrf_exempt
@require_GET
def stremio_addon_catalog(
    request,
    token,
    media_type,
    catalog_id,
    extra=None,
    config=None,
):
    """Serve a Floppy Watchlist catalog to Stremio."""
    user, grant = stremio_catalog.resolve_addon_credential(token)
    if user is None:
        logger.warning("Invalid token on Stremio addon catalog request")
        return _stremio_addon_response(
            {"error": "Invalid token"},
            status=401,
        )

    spec = stremio_catalog.get_catalog_spec(media_type, catalog_id)
    if spec is None:
        return _stremio_addon_response({"metas": []})

    if grant is not None:
        if not grant.allows_catalog(catalog_id):
            # Not 403: the add-on protocol has no way to show one, and an empty
            # catalog is the honest answer for something this install may not see.
            logger.info(
                "stremio_catalog grant_scope_excluded catalog_id=%s",
                catalog_id,
            )
            return _stremio_addon_response({"metas": []})
        stremio_catalog.touch_grant(grant)

    try:
        skip = stremio_catalog.parse_skip(extra)
    except ValueError as error:
        return _stremio_addon_response({"error": str(error)}, status=400)

    metas, unresolved_count = stremio_catalog.project_catalog(user, spec, skip)
    logger.info(
        "Stremio catalog projection catalog_id=%s skip=%s returned=%s unresolved=%s",
        catalog_id,
        skip,
        len(metas),
        unresolved_count,
    )
    return _stremio_addon_response({"metas": metas})


@login_not_required
@require_GET
def stremio_addon_configure(request, token, config=None):
    """Serve the addon configuration page for a user's install URL."""
    try:
        user = users.models.User.objects.get(token=token, is_active=True)
    except ObjectDoesNotExist:
        logger.warning("Invalid token on Stremio addon configure request")
        return HttpResponse("Invalid token", status=401)

    return render(
        request,
        "integrations/stremio_configure.html",
        {
            "catalog_options": stremio_catalog.catalog_options(user),
            "selected_ids": list(stremio_catalog.parse_catalog_config(config)),
        },
    )


@login_not_required
@csrf_exempt
@require_GET
def stremio_addon_manifest(request, token, config=None):
    """Serve the Stremio addon manifest for a user's install URL."""
    user, grant = stremio_catalog.resolve_addon_credential(token)
    if user is None:
        logger.warning("Invalid token on Stremio addon manifest request")
        return _stremio_addon_response({"error": "Invalid token"}, status=401)

    if grant is not None:
        stremio_catalog.touch_grant(grant)

    selected = stremio_catalog.parse_catalog_config(config)
    manifest = STREMIO_ADDON_MANIFEST | {
        "logo": request.build_absolute_uri(
            static("favicon/apple-touch-icon.png"),
        ),
        # Both gates: the install URL picks the catalogs, the grant bounds them.
        "catalogs": stremio_catalog.manifest_catalogs_for_grant(
            user,
            grant,
            selected,
        ),
    }
    return _stremio_addon_response(manifest)


@login_not_required
@csrf_exempt
@require_GET
def stremio_addon_meta(request, token, media_type, media_id):
    """Serve metadata for one item the user tracks."""
    user, grant = stremio_catalog.resolve_addon_credential(token)
    if user is None:
        logger.warning("Invalid token on Stremio addon meta request")
        return _stremio_addon_response({"error": "Invalid token"}, status=401)

    media_id = unquote(media_id)
    if (
        media_type not in {"movie", "series"}
        or len(media_id) > STREMIO_MAX_MEDIA_ID_LENGTH
        or not STREMIO_MEDIA_ID_PATTERN.fullmatch(media_id)
    ):
        return _stremio_addon_response({"meta": {}}, status=400)

    if grant is not None:
        stremio_catalog.touch_grant(grant)

    meta = stremio_catalog.project_meta(user, media_type, media_id, grant=grant)
    if meta is None:
        # Empty rather than 404: the item is simply not in this library, and
        # Stremio treats a 404 as the add-on being broken.
        return _stremio_addon_response({"meta": {}})

    return _stremio_addon_response({"meta": meta})


@login_not_required
@csrf_exempt
@require_GET
def stremio_addon_subtitles(request, token, media_type, media_id, config=None):
    """Record a playback-start scrobble from a Stremio subtitles request."""
    from django.core.cache import cache

    user, grant = stremio_catalog.resolve_addon_credential(token)
    if user is None:
        logger.warning("Invalid token on Stremio addon subtitles request")
        return _stremio_addon_response({"error": "Invalid token"}, status=401)
    if grant is not None and not grant.allow_playback_start:
        # This route records a playback start, which is a write. A grant minted
        # without that permission serves catalogs and nothing else.
        logger.info("stremio_subtitles rejected reason=grant_excludes_playback_start")
        return _stremio_addon_response({"subtitles": []})

    media_id = unquote(media_id)
    if (
        media_type not in {"movie", "series"}
        or len(media_id) > STREMIO_MAX_MEDIA_ID_LENGTH
        or not STREMIO_MEDIA_ID_PATTERN.fullmatch(media_id)
        or (media_type == "movie" and ":" in media_id)
    ):
        logger.info(
            "stremio_queue status=limited reason=invalid_media_id user_id=%s "
            "media_type=%s media_id=%s",
            user.id,
            media_type,
            media_id[:STREMIO_MAX_MEDIA_ID_LENGTH],
        )
        return _stremio_addon_response({"subtitles": []})

    # Stremio re-requests subtitles on seeks and quality changes; only the
    # first request per item in the window records a scrobble.
    throttle_key = f"stremio_scrobble_{user.id}_{media_type}_{media_id}"
    throttle_added = cache.add(
        throttle_key,
        "1",
        timeout=STREMIO_SCROBBLE_THROTTLE_SECONDS,
    )
    if throttle_added is None:
        logger.info(
            "stremio_queue status=unavailable reason=throttle_cache user_id=%s",
            user.id,
        )
    elif throttle_added:
        queue_member = stremio_queue.member(media_type, media_id)
        queue_status = stremio_queue.reserve_pending(user.id, queue_member)
        if queue_status == "accepted":
            try:
                tasks.process_stremio_webhook.delay(
                    {"id": media_id, "type": media_type},
                    user.id,
                    queue_member,
                )
                logger.info(
                    "stremio_queue status=queued user_id=%s media_type=%s media_id=%s",
                    user.id,
                    media_type,
                    media_id,
                )
            except Exception:
                stremio_queue.release_pending(user.id, queue_member)
                logger.exception(
                    "stremio_queue status=dispatch_failed user_id=%s media_type=%s "
                    "media_id=%s",
                    user.id,
                    media_type,
                    media_id,
                )
        else:
            logger.info(
                "stremio_queue status=%s user_id=%s media_type=%s media_id=%s",
                queue_status,
                user.id,
                media_type,
                media_id,
            )

    return _stremio_addon_response({"subtitles": []})


@app_helpers.answers_json
@require_POST
def sync_direction_settings(request):
    """Set which way watched state may travel for one connection.

    The chosen direction is intersected with what the provider's adapter can
    actually do, so picking "Both" on a read-only connection grants the reads
    and grants no writes — rather than recording an approval that would never
    be honoured and reporting it as if it had been.
    """
    from integrations.state import settings_view

    binding = SyncBinding.objects.filter(
        pk=request.POST.get("binding_id"),
        user=request.user,
    ).first()
    if binding is None:
        messages.error(request, "That connection no longer exists.")
        return redirect("integrations")

    direction = request.POST.get("direction", settings_view.DIRECTION_OFF)
    if direction not in settings_view.DIRECTION_LABELS:
        messages.error(request, "Unknown synchronization direction.")
        return redirect("integrations")

    try:
        partially_granted = settings_view.set_binding_direction(binding, direction)
    except settings_view.DirectionNotSupportedError:
        messages.error(
            request,
            (
                f"{binding.get_client_kind_display()} cannot do that yet. "
                "Its adapter reports no matching capability."
            ),
        )
        return redirect("integrations")

    if direction == settings_view.DIRECTION_OFF:
        messages.success(
            request,
            f"Turned off watched-state sync for {binding.get_client_kind_display()}.",
        )
    elif partially_granted:
        messages.warning(
            request,
            (
                f"Enabled what {binding.get_client_kind_display()} supports. "
                "The rest is listed as unavailable until its adapter is verified."
            ),
        )
    else:
        messages.success(
            request,
            f"Updated watched-state sync for {binding.get_client_kind_display()}.",
        )
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def sync_kill_switch(request):
    """Stop or resume one connection without discarding its approvals."""
    binding = SyncBinding.objects.filter(
        pk=request.POST.get("binding_id"),
        user=request.user,
    ).first()
    if binding is None:
        messages.error(request, "That connection no longer exists.")
        return redirect("integrations")

    binding.kill_switch = request.POST.get("kill_switch") == "on"
    binding.save(update_fields=["kill_switch", "updated_at"])

    if binding.kill_switch:
        messages.info(
            request,
            f"Paused {binding.get_client_kind_display()}. Your settings are kept.",
        )
    else:
        messages.success(request, f"Resumed {binding.get_client_kind_display()}.")
    return redirect("integrations")


@app_helpers.answers_json
@require_POST
def sync_resolve_conflict(request):
    """Settle one held disagreement with the state the user chose."""
    from integrations.state.apply import resolve_conflict

    conflict = StateConflict.objects.filter(
        pk=request.POST.get("conflict_id"),
        user=request.user,
        status=StateConflictStatus.OPEN.value,
    ).first()
    if conflict is None:
        messages.error(request, "That conflict is no longer open.")
        return redirect("integrations")

    watched = request.POST.get("watched") == "true"
    resolve_conflict(conflict, watched=watched)
    messages.success(
        request,
        f"Resolved. {conflict.item} is now marked "
        f"{'watched' if watched else 'unwatched'}.",
    )
    return redirect("integrations")


def _match_source_for_user(request, item_id):
    """Return a movie/TV source item that this user actually tracks."""
    item = get_object_or_404(
        Item,
        pk=item_id,
        media_type__in=(MediaTypes.MOVIE.value, MediaTypes.TV.value),
    )
    tracked = (
        Movie.objects.filter(user=request.user, item=item).exists()
        if item.media_type == MediaTypes.MOVIE.value
        else TV.objects.filter(user=request.user, item=item).exists()
    )
    if not tracked:
        from django.http import Http404

        raise Http404
    return item


def _match_destination_from_result(result, media_type):
    """Materialize a same-type TMDB search result for preview/apply."""
    media_id = result.get("media_id") or result.get("id")
    title = result.get("title") or result.get("name")
    if not media_id or not title:
        return None
    defaults = {
        "title": title,
        "original_title": result.get("original_title") or result.get("original_name"),
        "localized_title": result.get("localized_title"),
        "image": result.get("image") or result.get("poster_path") or "",
    }
    destination, _created = Item.objects.get_or_create(
        media_id=str(media_id),
        source=Sources.TMDB.value,
        media_type=media_type,
        defaults=defaults,
    )
    return destination


def _match_candidate_rows(results):
    """Return renderable destination rows without persisting any Item.

    Rendering used to hand the template an Item pk per result, which meant a
    search wrote one Item (and its later metadata fan-out) for every hit.
    """
    rows = []
    for result in results:
        media_id = result.get("media_id") or result.get("id")
        title = result.get("title") or result.get("name")
        if not media_id or not title:
            continue
        rows.append({"media_id": str(media_id), "title": title, "result": result})
    return rows


def _match_reference_ids(user, source_item):
    """Return only this user's source references affected by the correction."""
    item_ids = [source_item.pk]
    if source_item.media_type == MediaTypes.TV.value:
        item_ids.extend(
            Item.objects.filter(
                media_id=source_item.media_id,
                source=source_item.source,
                media_type=MediaTypes.EPISODE.value,
            ).values_list("pk", flat=True),
        )
    return list(
        ExternalReference.objects.filter(
            user=user,
        ).filter(
            Q(matched_item_id__in=item_ids) | Q(corrected_item_id__in=item_ids),
        ).values_list("id", flat=True),
    )


@login_required
def match_fix(request, item_id):
    """Search, preview, and apply a same-type match correction."""
    source_item = _match_source_for_user(request, item_id)
    query = request.GET.get("q", "").strip()
    candidates = []
    if query:
        try:
            candidates = services.search(
                source_item.media_type,
                query,
                1,
                source=Sources.TMDB.value,
                user=request.user,
            ).get("results", [])
        except services.ProviderAPIError as error:
            messages.error(request, f"Could not search TMDB: {error}")

    candidate_rows = _match_candidate_rows(candidates)

    preview = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "preview":
            chosen = next(
                (
                    row
                    for row in candidate_rows
                    if row["media_id"] == request.POST.get("destination_media_id")
                ),
                None,
            )
            destination = (
                _match_destination_from_result(chosen["result"], source_item.media_type)
                if chosen
                else None
            )
            if destination is None:
                messages.error(request, "Choose a valid same-type destination.")
            else:
                try:
                    mapping = json.loads(request.POST.get("mapping_json") or "{}")
                    preview = preview_match_correction(
                        request.user,
                        source_item,
                        destination,
                        episode_mapping=mapping or None,
                    )
                    request.session["match_correction_preview"] = {
                        "source_item_id": source_item.pk,
                        "destination_item_id": destination.pk,
                        "token": preview["token"],
                        "reference_ids": _match_reference_ids(
                            request.user,
                            source_item,
                        ),
                    }
                except (ValueError, json.JSONDecodeError) as error:
                    messages.error(request, str(error))
        elif action == "apply":
            stored = request.session.get("match_correction_preview") or {}
            if stored.get("source_item_id") != source_item.pk:
                messages.error(request, "Refresh the correction preview before applying.")
            else:
                try:
                    mapping = json.loads(request.POST.get("mapping_json") or "{}")
                    decisions = {
                        key.removeprefix("decision_"): value
                        for key, value in request.POST.items()
                        if key.startswith("decision_") and value
                    }
                    destination_item = apply_match_correction(
                        request.user,
                        stored["source_item_id"],
                        stored["destination_item_id"],
                        stored["token"],
                        episode_mapping=mapping or None,
                        decisions=decisions,
                        reference_ids=stored.get("reference_ids", []),
                        note=request.POST.get("note", ""),
                    )
                except (
                    InvalidMatchCorrectionError,
                    MissingEpisodeMappingError,
                    StaleCorrectionPreviewError,
                ) as error:
                    messages.error(request, str(error))
                else:
                    request.session.pop("match_correction_preview", None)
                    messages.success(
                        request,
                        "Match corrected and future imports mapped.",
                    )
                    return redirect(
                        "media_details",
                        source=Sources.TMDB.value,
                        media_type=source_item.media_type,
                        media_id=destination_item.media_id,
                        title=destination_item.title,
                    )

    context = {
        "source_item": source_item,
        "candidates": candidate_rows,
        "preview": preview,
        "preview_mapping_json": (
            json.dumps(preview["episode_mapping"], sort_keys=True)
            if preview
            else ""
        ),
        "reference_count": len(_match_reference_ids(request.user, source_item)),
    }
    return render(request, "integrations/match_fix.html", context)


@app_helpers.answers_json
@login_required
@require_POST
def match_reference_status(request, reference_id, status):
    """Ignore or restore one user-scoped external reference."""
    reference = get_object_or_404(
        ExternalReference,
        pk=reference_id,
        user=request.user,
    )
    if status == ExternalReferenceReviewStatus.IGNORED.value:
        reference.review_status = status
        reference.save(update_fields=["review_status", "updated_at"])
        messages.success(request, "Future imports will ignore this source identity.")
    elif status == "remove":
        reference.review_status = ExternalReferenceReviewStatus.RESOLVED.value
        reference.corrected_item = None
        reference.episode_mapping = {}
        reference.decision_note = ""
        reference.save(
            update_fields=[
                "review_status",
                "corrected_item",
                "episode_mapping",
                "decision_note",
                "updated_at",
            ],
        )
        messages.success(request, "The saved correction was removed.")
    else:
        messages.error(request, "Unknown match decision.")
    return redirect("integrations")
