"""Settings > Import for the web (v2 P4-K).

The screen reads what import_data.html renders: the import settings, the
source tiles and, per source the web draws, what its dialog needs. Sources
the web does not draw yet open the Django page's dialog (`?open=<key>`).
The activity panel is `import_data_activity` with `Accept: application/json`.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import gettext as _
from rest_framework import serializers

# Sources the web draws (K1-K3: all of them); a tile it did not draw would
# open the Django page's dialog.
WEB_SOURCES = frozenset(
    {
        "plex",
        "radarr",
        "sonarr",
        "stremio",
        "audiobookshelf",
        "storyteller",
        "koreader",
        "trakt",
        "anilist",
        "lastfm",
        "koito",
        "steam",
        "xbox",
        "psn",
        "pocketcasts",
        "gpodder",
        "yamtrack",
        "yamtrack_native",
        "clz",
        "hltb",
        "grouvee",
        "imdb",
        "goodreads",
        "hardcover",
        "storygraph",
        "tvtime",
        "myanimelist",
        "kitsu",
        "simkl",
        "mdblist",
    }
)

MEDIA_TAGS = (
    ("all", "All Sources"),
    ("screen", "Movies & TV"),
    ("anime_manga", "Anime & Manga"),
    ("reading", "Books & Comics"),
    ("games", "Games"),
    ("podcasts", "Podcasts"),
    ("music", "Music"),
    ("backup", "Backups"),
)
_EVERYTHING = ["backup", "screen", "anime_manga", "reading", "games", "podcasts", "music"]

# key, name, tags, logo (static path, "" for none), description
TILES = (
    ("plex", "Plex", ["screen", "music"], "img/plex-logo.svg", "Import watch and listen history from Plex."),
    ("radarr", "Radarr", ["screen"], "img/plex-logo.svg", "Import owned movies from Radarr."),
    ("sonarr", "Sonarr", ["screen"], "img/plex-logo.svg", "Import owned TV shows from Sonarr."),
    ("stremio", "Stremio", ["screen"], "img/stremio-logo.svg", "Import watched movies and episodes from Stremio."),
    (
        "audiobookshelf",
        "Audiobookshelf",
        ["books", "podcasts"],
        "img/audiobookshelf-logo.svg",
        "Import audiobook progress from Audiobookshelf.",
    ),
    ("storyteller", "Storyteller", ["reading"], "img/storyteller-logo.svg", "Import reading progress from Storyteller."),
    (
        "koreader",
        "KOReader",
        ["reading"],
        "img/koreader-logo.svg",
        "Sync book reading progress from a KOReader sync server.",
    ),
    ("pocketcasts", "Pocket Casts", ["podcasts"], "img/pocketcasts-logo.svg", "Import podcast progress from Pocket Casts."),
    ("gpodder", "GPodder", ["podcasts"], "favicon/apple-touch-icon.png", "Import podcast history from GPodder."),
    ("lastfm", "Last.fm", ["music"], "img/lastfm-logo.png", "Import listening history from Last.fm."),
    ("koito", "Koito", ["music"], "img/koito-logo.svg", "Import listening history from a self-hosted Koito server."),
    ("trakt", "Trakt", ["screen"], "img/trakt-logo.svg", "Import movies and TV shows from Trakt."),
    ("mdblist", "MDBList", ["screen"], "img/mdblist-logo.png", "Import watch history and ratings from MDBList."),
    ("simkl", "SIMKL", ["screen", "anime_manga"], "img/simkl-logo.png", "Import movies, TV shows and anime from Simkl."),
    ("myanimelist", "MyAnimeList", ["anime_manga"], "img/mal-logo.ico", "Import anime and manga from MyAnimeList."),
    ("anilist", "AniList", ["anime_manga"], "img/anilist-logo.svg", "Import anime and manga from AniList."),
    ("kitsu", "Kitsu", ["anime_manga"], "img/kitsu-logo.png", "Import anime and manga from Kitsu."),
    ("yamtrack", "Floppy", _EVERYTHING, "favicon/apple-touch-icon.png", "Import a backup from Floppy."),
    ("yamtrack_native", "Yamtrack", _EVERYTHING, "img/yamtrack-logo.png", "Import a CSV export from Yamtrack."),
    ("clz", "CLZ", ["backup", "screen", "reading", "games"], "", "Import a CLZ (Collectorz) CSV or XML export."),
    ("hltb", "HowLongToBeat", ["games"], "img/hltb-logo.png", "Import games from HowLongToBeat."),
    ("grouvee", "Grouvee", ["games"], "img/grouvee_logo.png", "Import games from Grouvee."),
    ("steam", "Steam", ["games"], "img/steam-logo.ico", "Import games from Steam."),
    ("xbox", "Xbox", ["games"], "img/xbox-logo.svg", "Sync played games and hours from Xbox."),
    ("psn", "PlayStation", ["games"], "img/playstation-logo.svg", "Sync played games and hours from PlayStation."),
    ("imdb", "IMDB", ["screen"], "img/imdb-logo.png", "Import ratings from IMDB."),
    ("tvtime", "TV Time", ["screen"], "img/tvtime-logo.png", "Import watch history from a TV Time data export."),
    ("goodreads", "Goodreads", ["reading"], "img/logo-goodreads.svg", "Import a backup from Goodreads."),
    ("hardcover", "Hardcover", ["reading"], "img/hardcover-logo.png", "Import an export from Hardcover."),
    ("storygraph", "StoryGraph", ["reading"], "img/storygraph-logo.svg", "Import an export from StoryGraph."),
)

MODE_LABELS = {
    "new": "Only New Items",
    "overwrite": "Overwrite Existing",
    "update_collection": "Collection Metadata Only",
    "watchlist": "Watchlist Sync",
}


def _static(path: str) -> str:
    from django.templatetags.static import static

    return static(path) if path else ""


def _connected(user) -> dict[str, bool]:
    from app.providers import credentials

    def flag(attr, check="is_connected"):
        account = getattr(user, attr, None)
        try:
            return bool(account and getattr(account, check))
        except Exception:
            return False

    plex = getattr(user, "plex_account", None)
    return {
        "plex": bool(plex and plex.plex_token),
        "stremio": flag("stremio_account"),
        "audiobookshelf": flag("audiobookshelf_account"),
        "storyteller": flag("storyteller_account"),
        "koreader": flag("koreader_account"),
        "pocketcasts": flag("pocketcasts_account"),
        "gpodder": flag("gpodder_account"),
        "lastfm": flag("lastfm_account"),
        "koito": flag("koito_account"),
        "mdblist": flag("mdblist_account"),
        "xbox": flag("xbox_account"),
        "psn": flag("psn_account"),
        "hardcover": credentials.has_user_value("hardcover", user),
    }


def build_import(request) -> dict:
    """Import: settings, the source tiles, and what the web's dialogs need."""
    from users.models import ImportFrequencyChoices, ImportModeChoices

    user = request.user
    connected = _connected(user)
    django_url = reverse("import_data")
    mode_hints = {
        "new": _(
            "Only adds items you don't have yet. Never changes or deletes anything already in your library, "
            "even if it looks incomplete."
        ),
        "overwrite": _("Replaces matching items with the imported version. Items not in this file are left alone."),
        "watchlist": _("Only imports your watchlist. Doesn't touch watch history, ratings, or anything else."),
        "update_collection": _(
            "Only updates collection metadata (e.g. physical/digital copies you own). "
            "Doesn't touch watch history or ratings."
        ),
    }
    return {
        "is_demo": user.is_demo,
        "settings": {
            "frequency": user.import_frequency,
            "time": user.import_time or "00:00",
            "mode": user.import_mode,
            "frequency_choices": [{"value": v, "label": str(label), "hint": ""} for v, label in ImportFrequencyChoices.choices],
            "mode_choices": [
                {"value": v, "label": str(label), "hint": str(mode_hints.get(v, ""))} for v, label in ImportModeChoices.choices
            ],
            "save_url": reverse("save_import_settings"),
        },
        "media_tags": [{"value": value, "label": str(_(label))} for value, label in MEDIA_TAGS],
        "tiles": [
            {
                "key": key,
                "name": name,
                "tags": list(tags),
                "logo": _static(logo),
                "description": str(_(description)),
                "connected": bool(connected.get(key, False)),
                "badge": str(_("Configured")) if key == "hardcover" else str(_("Connected")),
                "web": key in WEB_SOURCES,
                "django_url": f"{django_url}?open={key}",
            }
            for key, name, tags, logo, description in TILES
        ],
        "mdblist_connected": connected["mdblist"],
        "hardcover_key_saved": connected["hardcover"],
        "trakt": _trakt(request),
        **_lastfm_poll(user),
        "audiobookshelf_poll_interval": _audiobookshelf_poll(user),
        "accounts": _accounts(user),
        "plex": _plex(user),
        "radarr": _arr(user.radarr_instances, "radarr"),
        "sonarr": _arr(user.sonarr_instances, "sonarr"),
        "storyteller_pending": _storyteller_pending(request),
        "koreader": _koreader(user),
        "activity": _activity_or_none(user),
        "urls": {
            "template": reverse("import_template_csv"),
            "activity": reverse("import_data_activity"),
            "onboarding": reverse("onboarding_service_setup"),
            "restart_setup": reverse("onboarding_restart"),
            "guide": "https://github.com/dannyvfilms/Floppy/wiki/4.-Integrations#import-overview",
            "csv_docs": "https://github.com/dannyvfilms/Floppy/wiki/6.-Admin-and-Operations#csv-import-floppy--yamtrack-format",
            "yamtrack": reverse("import_yamtrack"),
            "clz": reverse("import_clz"),
            "hltb": reverse("import_hltb"),
            "grouvee": reverse("import_grouvee"),
            "imdb": reverse("import_imdb"),
            "goodreads": reverse("import_goodreads"),
            "hardcover": reverse("import_hardcover"),
            "storygraph": reverse("import_storygraph"),
            "tvtime": reverse("import_tvtime"),
            "mal": reverse("import_mal"),
            "kitsu": reverse("import_kitsu"),
            "mdblist": reverse("import_mdblist"),
            "simkl": reverse("simkl_oauth"),
            "trakt_public": reverse("import_trakt_public"),
            "trakt_oauth": reverse("trakt_oauth"),
            "trakt_export": reverse("import_trakt_export_file"),
            "anilist_public": reverse("import_anilist_public"),
            "anilist_oauth": reverse("import_anilist_oauth"),
            "steam": reverse("import_steam"),
            "lastfm_connect": reverse("lastfm_connect"),
            "lastfm_disconnect": reverse("lastfm_disconnect"),
            "lastfm_sync": reverse("poll_lastfm_manual"),
            "lastfm_history": reverse("import_lastfm_history"),
            "koito_connect": reverse("koito_connect"),
            "koito_disconnect": reverse("koito_disconnect"),
            "koito_sync": reverse("poll_koito_manual"),
            "koito_history": reverse("import_koito_history"),
            "xbox_connect": reverse("xbox_connect"),
            "xbox_disconnect": reverse("xbox_disconnect"),
            "xbox_sync": reverse("import_xbox"),
            "psn_connect": reverse("psn_connect"),
            "psn_disconnect": reverse("psn_disconnect"),
            "psn_sync": reverse("import_psn"),
            "pocketcasts_connect": reverse("pocketcasts_connect"),
            "pocketcasts_disconnect": reverse("pocketcasts_disconnect"),
            "pocketcasts_sync": reverse("import_pocketcasts"),
            "gpodder_connect": reverse("gpodder_connect"),
            "gpodder_disconnect": reverse("gpodder_disconnect"),
            "gpodder_sync": reverse("import_gpodder"),
            "plex_connect": reverse("plex_connect"),
            "plex_disconnect": reverse("plex_disconnect"),
            "plex_import": reverse("import_plex"),
            "plex_disable_watchlist": reverse("plex_disable_watchlist"),
            "plex_status": reverse("import_data_plex_status"),
            "plex_sections": reverse("import_data_plex_sections"),
            "radarr_connect": reverse("radarr_connect"),
            "radarr_disconnect": reverse("radarr_disconnect"),
            "radarr_sync": reverse("import_radarr"),
            "sonarr_connect": reverse("sonarr_connect"),
            "sonarr_disconnect": reverse("sonarr_disconnect"),
            "sonarr_sync": reverse("import_sonarr"),
            "stremio_connect": reverse("stremio_connect"),
            "stremio_disconnect": reverse("stremio_disconnect"),
            "stremio_sync": reverse("import_stremio"),
            "audiobookshelf_connect": reverse("audiobookshelf_connect"),
            "audiobookshelf_disconnect": reverse("audiobookshelf_disconnect"),
            "audiobookshelf_sync": reverse("import_audiobookshelf"),
            "storyteller_connect": reverse("storyteller_connect"),
            "storyteller_poll": reverse("storyteller_poll"),
            "storyteller_cancel": reverse("storyteller_cancel"),
            "storyteller_disconnect": reverse("storyteller_disconnect"),
            "storyteller_sync": reverse("import_storyteller"),
            "koreader_connect": reverse("koreader_connect"),
            "koreader_settings": reverse("koreader_settings"),
            "koreader_disconnect": reverse("koreader_disconnect"),
            "koreader_sync": reverse("import_koreader"),
        },
    }


def _audiobookshelf_poll(user) -> int:
    """Audiobookshelf: the poll interval in minutes (the recurring task's, when it runs)."""
    from django.conf import settings

    interval = getattr(settings, "AUDIOBOOKSHELF_POLL_INTERVAL_MINUTES", 15)
    if getattr(user, "audiobookshelf_account", None):
        from django_celery_beat.models import PeriodicTask

        from integrations.task_filters import user_kwargs_regex

        task = PeriodicTask.objects.filter(
            task="Import from Audiobookshelf (Recurring)",
            kwargs__regex=user_kwargs_regex(user.id),
            enabled=True,
        ).first()
        if task and task.interval:
            interval = task.interval.every
    return interval


def _plex_label(section) -> str:
    label = section.get("title") or _("Unknown library")
    if section.get("server_name"):
        label += f" - {section['server_name']}"
    if section.get("type"):
        kind = str(section["type"])
        label += f" ({kind[:1].upper()}{kind[1:]})"
    return label


def plex_libraries(sections) -> list[dict]:
    """Return Plex libraries as the Import dialog lists them; never the server URI or token."""
    return [
        {
            "value": f"{section.get('machine_identifier')}::{section.get('id')}",
            "label": _plex_label(section),
            "is_music": bool(section.get("is_music")),
            "audiobook_hint": bool(section.get("audiobook_hint")),
            "content_kind": str(section.get("content_kind") or "auto"),
        }
        for section in sections
    ]


def _plex(user):
    """Plex: the connected account, its cached libraries and watchlist sync (no network)."""
    from integrations.plex_watchlist import WATCHLIST_SYNC_INTERVAL_MINUTES
    from users.views import _decorate_plex_sections, _get_stored_plex_account

    account = _get_stored_plex_account(user)
    if not account:
        return None
    return {
        "username": account.plex_username or "",
        "usernames": user.plex_usernames or "",
        "libraries": plex_libraries(_decorate_plex_sections(account.sections or [], account)),
        "watchlist_sync_enabled": bool(account.watchlist_sync_enabled),
        "watchlist_last_synced_at": _when(account.watchlist_last_synced_at),
        "watchlist_last_error": account.watchlist_last_error or "",
        "watchlist_interval": WATCHLIST_SYNC_INTERVAL_MINUTES,
    }


def _arr(instances, label) -> list[dict]:
    """Radarr or Sonarr instances: name, server, state; never the API key."""
    return [
        {
            "id": instance.pk,
            "name": instance.display_name,
            "base_url": instance.base_url,
            "connected": bool(instance.is_connected()),
            "error": instance.last_error_message or "",
            "last_sync": _when(instance.last_sync_at),
        }
        for instance in instances.order_by("created_at")
    ]


def _storyteller_pending(request):
    """Return a Storyteller device login waiting for approval (never the device code)."""
    pending = request.session.get("storyteller_pending_auth")
    if not pending:
        return None
    return {
        "user_code": str(pending.get("user_code") or ""),
        "verification_uri": str(pending.get("verification_uri_complete") or pending.get("verification_uri") or ""),
        "interval": int(pending.get("interval") or 5),
    }


def _koreader(user):
    """KOReader: the saved settings (never the password) and the linked document count."""
    account = getattr(user, "koreader_account", None)
    if not account:
        return None
    from integrations.models import KoreaderDocumentLink

    return {
        "server_url": account.server_url,
        "username": account.username,
        "verify_ssl": bool(account.verify_ssl),
        "create_missing": bool(account.create_missing),
        "skip_finished_books": bool(account.skip_finished_books),
        "finished_threshold_percent": round((account.finished_threshold or 0) * 100),
        "link_count": KoreaderDocumentLink.objects.filter(user=user).count(),
    }


def _trakt(request) -> dict:
    """Trakt: whether username and OAuth imports are possible, and the callback to register.

    Trakt refuses non-HTTPS redirect URIs, so such instances use the device
    code flow (as import_data).
    """
    from app import helpers
    from app.providers import credentials
    from integrations.imports import trakt as trakt_imports

    redirect_uri = helpers.build_absolute_app_url(request, reverse("import_trakt_private"))
    capable = helpers.supports_oauth_redirect(redirect_uri)
    return {
        "configured": bool(credentials.get("trakt", "client_id") and credentials.get("trakt", "client_secret")),
        "redirect_uri": redirect_uri if capable else trakt_imports.TRAKT_OOB_REDIRECT_URI,
        "redirect_capable": capable,
    }


def _lastfm_poll(user) -> dict:
    """Last.fm: the poll interval in minutes and the recurring task's, when it runs."""
    from django.conf import settings

    interval = getattr(settings, "LASTFM_POLL_INTERVAL_MINUTES", 15)
    every = None
    if getattr(user, "lastfm_account", None):
        from django_celery_beat.models import PeriodicTask

        task = PeriodicTask.objects.filter(task="Poll Last.fm for all users", enabled=True).first()
        if task and task.interval:
            interval = every = task.interval.every
    return {"lastfm_poll_interval": interval, "lastfm_recurring_every": every}


def history_state(account, *, pages: bool = False) -> dict:
    """Return a full-history import (Last.fm, Koito), labelled as import_data does."""
    status = account.history_import_status
    current = total = None
    if pages and account.history_import_total_pages:
        total = account.history_import_total_pages
        if status == "completed":
            current = total
        elif account.history_import_next_page:
            current = min(account.history_import_next_page, total)
    return {
        "status": status,
        "label": "Not started" if status == "idle" else str(account.get_history_import_status_display()),
        "current_page": current,
        "total_pages": total,
        "completed_at": _when(account.history_import_completed_at),
        "error": (account.history_import_last_error_message or "") if status == "failed" else "",
        "can_start": bool(account.history_import_can_start),
        "button": "Reimport full history" if status in {"completed", "failed"} else "Import full history",
    }


def _accounts(user) -> dict:
    """Return the accounts as their dialogs show them; never a key, token or password."""

    def account(attr, *, name="", error_when_broken=True, history=False, pages=False):
        row = getattr(user, attr, None)
        if not row:
            return None
        broken = bool(getattr(row, "connection_broken", False))
        error = getattr(row, "last_error_message", "") or ""
        return {
            "connected": bool(row.is_connected),
            "broken": broken,
            "name": str(getattr(row, name, "") or "") if name else "",
            "last_sync": _when(row.last_sync_at),
            "error": error if (broken or not error_when_broken) else "",
            "history": history_state(row, pages=pages) if history else None,
        }

    return {
        "lastfm": account("lastfm_account", history=True, pages=True),
        "koito": account("koito_account", name="base_url", history=True),
        "xbox": account("xbox_account", name="gamertag", error_when_broken=False),
        "psn": account("psn_account", name="online_id", error_when_broken=False),
        "pocketcasts": account("pocketcasts_account"),
        "gpodder": account("gpodder_account"),
        "stremio": account("stremio_account", error_when_broken=False),
        "audiobookshelf": account("audiobookshelf_account", name="base_url", error_when_broken=False),
        "storyteller": account("storyteller_account", name="server_url", error_when_broken=False),
        "koreader": account("koreader_account", name="server_url", error_when_broken=False),
    }


def _activity_or_none(user):
    """Return the first activity snapshot, or None when Celery's result store is down.

    The page must still open; the panel polls `import_data_activity` and
    shows the activity once it answers.
    """
    import logging

    try:
        return build_import_activity(user)
    except Exception:  # a broker or result-store outage must not fail the page
        logging.getLogger(__name__).warning("Import activity unavailable for the settings screen", exc_info=True)
        return None


def _when(value):
    return value.isoformat() if value else None


def _text(value) -> str:
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        return "\n".join(str(line) for line in value)
    return str(value)


def _source(key) -> dict:
    from users.templatetags.user_tags import SOURCES_CONFIG

    info = SOURCES_CONFIG.get(key or "")
    return {"key": key or "", "name": info["name"] if info else (key or ""), "logo": info["logo"] if info else ""}


def build_import_activity(user) -> dict:
    """Return the activity panel: schedules, recent results, runs, imported media."""
    from integrations.models import ImportRun
    from users.views import _import_source_media_summary

    tasks = user.get_import_tasks()
    runs = ImportRun.objects.filter(user=user).order_by("-started_at")[:10]
    return {
        "schedules": [
            {
                "task_name": schedule["task"].name,
                "source": _source(schedule.get("source")),
                "schedule": str(schedule.get("schedule") or ""),
                "username": str(schedule.get("username") or ""),
                "mode": MODE_LABELS.get(schedule.get("mode"), str(schedule.get("mode") or "")),
                "last_run": _when(schedule.get("last_run")),
                "next_run": _when(schedule.get("next_run")),
            }
            for schedule in tasks["schedules"]
        ],
        "results": [
            {
                "source": _source(result.get("source")),
                "date": _when(result.get("date")),
                "status": result.get("status") or "",
                "summary": _text(result.get("summary")),
                "errors": _text(result.get("errors")),
                "progress_current": result.get("progress_current") or 0,
                "progress_total": result.get("progress_total") or 0,
                "progress_label": str(result.get("progress_label") or ""),
                "progress_percent": result.get("progress_percent") or 0,
            }
            for result in tasks["results"]
        ],
        "runs": [
            {
                "id": run.pk,
                "source": _source(run.source),
                "status": run.status,
                "started_at": _when(run.started_at),
                "created": run.created_count or 0,
                "updated": run.updated_count or 0,
                "skipped": run.skipped_count or 0,
                "failed": run.failed_count or 0,
                "remaining": run.remaining_estimate,
                "cancel_url": reverse("cancel_import_run", args=[run.pk]),
                "rollback_url": reverse("rollback_import_run", args=[run.pk]),
            }
            for run in runs
        ],
        "source_media": [
            {
                "media_type": row["media_type"],
                "source": _source(row["source"]),
                "count": row["count"],
                "delete_url": reverse("bulk_delete_by_import_source", args=[row["media_type"], row["source"]]),
            }
            for row in _import_source_media_summary(user)
        ],
        "delete_schedule_url": reverse("delete_import_schedule"),
    }


class SettingsImportChoiceSerializer(serializers.Serializer):
    """An option (`hint`: its tooltip)."""

    value = serializers.CharField()
    label = serializers.CharField()
    hint = serializers.CharField(allow_blank=True)


class SettingsImportSettingsSerializer(serializers.Serializer):
    """Import Settings: each change posts all three to `save_url` (204)."""

    frequency = serializers.CharField()
    time = serializers.CharField()
    mode = serializers.CharField()
    frequency_choices = SettingsImportChoiceSerializer(many=True)
    mode_choices = SettingsImportChoiceSerializer(many=True)
    save_url = serializers.CharField()


class SettingsImportTagSerializer(serializers.Serializer):
    """A media-type filter."""

    value = serializers.CharField()
    label = serializers.CharField()


class SettingsImportTileSerializer(serializers.Serializer):
    """A source tile (`web`: the web draws its dialog; else open `django_url`)."""

    key = serializers.CharField()
    name = serializers.CharField()
    tags = serializers.ListField(child=serializers.CharField())
    logo = serializers.CharField(allow_blank=True)
    description = serializers.CharField()
    connected = serializers.BooleanField()
    badge = serializers.CharField()
    web = serializers.BooleanField()
    django_url = serializers.CharField()


class SettingsImportUrlsSerializer(serializers.Serializer):
    """Where the Import forms post (`simkl` leaves for Simkl's sign-in)."""

    template = serializers.CharField()
    activity = serializers.CharField()
    onboarding = serializers.CharField()
    restart_setup = serializers.CharField()
    guide = serializers.CharField()
    csv_docs = serializers.CharField()
    yamtrack = serializers.CharField()
    clz = serializers.CharField()
    hltb = serializers.CharField()
    grouvee = serializers.CharField()
    imdb = serializers.CharField()
    goodreads = serializers.CharField()
    hardcover = serializers.CharField()
    storygraph = serializers.CharField()
    tvtime = serializers.CharField()
    mal = serializers.CharField()
    kitsu = serializers.CharField()
    mdblist = serializers.CharField()
    simkl = serializers.CharField()
    trakt_public = serializers.CharField()
    trakt_oauth = serializers.CharField()
    trakt_export = serializers.CharField()
    anilist_public = serializers.CharField()
    anilist_oauth = serializers.CharField()
    steam = serializers.CharField()
    lastfm_connect = serializers.CharField()
    lastfm_disconnect = serializers.CharField()
    lastfm_sync = serializers.CharField()
    lastfm_history = serializers.CharField()
    koito_connect = serializers.CharField()
    koito_disconnect = serializers.CharField()
    koito_sync = serializers.CharField()
    koito_history = serializers.CharField()
    xbox_connect = serializers.CharField()
    xbox_disconnect = serializers.CharField()
    xbox_sync = serializers.CharField()
    psn_connect = serializers.CharField()
    psn_disconnect = serializers.CharField()
    psn_sync = serializers.CharField()
    pocketcasts_connect = serializers.CharField()
    pocketcasts_disconnect = serializers.CharField()
    pocketcasts_sync = serializers.CharField()
    gpodder_connect = serializers.CharField()
    gpodder_disconnect = serializers.CharField()
    gpodder_sync = serializers.CharField()
    plex_connect = serializers.CharField()
    plex_disconnect = serializers.CharField()
    plex_import = serializers.CharField()
    plex_disable_watchlist = serializers.CharField()
    plex_status = serializers.CharField()
    plex_sections = serializers.CharField()
    radarr_connect = serializers.CharField()
    radarr_disconnect = serializers.CharField()
    radarr_sync = serializers.CharField()
    sonarr_connect = serializers.CharField()
    sonarr_disconnect = serializers.CharField()
    sonarr_sync = serializers.CharField()
    stremio_connect = serializers.CharField()
    stremio_disconnect = serializers.CharField()
    stremio_sync = serializers.CharField()
    audiobookshelf_connect = serializers.CharField()
    audiobookshelf_disconnect = serializers.CharField()
    audiobookshelf_sync = serializers.CharField()
    storyteller_connect = serializers.CharField()
    storyteller_poll = serializers.CharField()
    storyteller_cancel = serializers.CharField()
    storyteller_disconnect = serializers.CharField()
    storyteller_sync = serializers.CharField()
    koreader_connect = serializers.CharField()
    koreader_settings = serializers.CharField()
    koreader_disconnect = serializers.CharField()
    koreader_sync = serializers.CharField()


class SettingsImportPlexLibrarySerializer(serializers.Serializer):
    """A Plex library (`value`: machine::id; music libraries take a content kind)."""

    value = serializers.CharField()
    label = serializers.CharField()
    is_music = serializers.BooleanField()
    audiobook_hint = serializers.BooleanField()
    content_kind = serializers.CharField()


class SettingsImportPlexSerializer(serializers.Serializer):
    """The connected Plex account (cached libraries; the dialog asks for live ones)."""

    username = serializers.CharField(allow_blank=True)
    usernames = serializers.CharField(allow_blank=True)
    libraries = SettingsImportPlexLibrarySerializer(many=True)
    watchlist_sync_enabled = serializers.BooleanField()
    watchlist_last_synced_at = serializers.DateTimeField(allow_null=True)
    watchlist_last_error = serializers.CharField(allow_blank=True)
    watchlist_interval = serializers.IntegerField()


class SettingsImportArrSerializer(serializers.Serializer):
    """A Radarr or Sonarr instance."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    base_url = serializers.CharField()
    connected = serializers.BooleanField()
    error = serializers.CharField(allow_blank=True)
    last_sync = serializers.DateTimeField(allow_null=True)


class SettingsImportStorytellerPendingSerializer(serializers.Serializer):
    """A Storyteller login waiting for approval; poll `urls.storyteller_poll`."""

    user_code = serializers.CharField(allow_blank=True)
    verification_uri = serializers.CharField(allow_blank=True)
    interval = serializers.IntegerField()


class SettingsImportKoreaderSerializer(serializers.Serializer):
    """KOReader's saved settings (a blank password keeps the saved one)."""

    server_url = serializers.CharField()
    username = serializers.CharField()
    verify_ssl = serializers.BooleanField()
    create_missing = serializers.BooleanField()
    skip_finished_books = serializers.BooleanField()
    finished_threshold_percent = serializers.IntegerField()
    link_count = serializers.IntegerField()


class SettingsImportTraktSerializer(serializers.Serializer):
    """Trakt: username and OAuth imports need the instance's Trakt app."""

    configured = serializers.BooleanField()
    redirect_uri = serializers.CharField()
    redirect_capable = serializers.BooleanField()


class SettingsImportHistorySerializer(serializers.Serializer):
    """A full-history import (`can_start`: show `button`)."""

    status = serializers.CharField()
    label = serializers.CharField()
    current_page = serializers.IntegerField(allow_null=True)
    total_pages = serializers.IntegerField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    error = serializers.CharField(allow_blank=True)
    can_start = serializers.BooleanField()
    button = serializers.CharField()


class SettingsImportAccountSerializer(serializers.Serializer):
    """A connected account (`name`: the server, the gamertag or the PSN online ID)."""

    connected = serializers.BooleanField()
    broken = serializers.BooleanField()
    name = serializers.CharField(allow_blank=True)
    last_sync = serializers.DateTimeField(allow_null=True)
    error = serializers.CharField(allow_blank=True)
    history = SettingsImportHistorySerializer(allow_null=True)


class SettingsImportAccountsSerializer(serializers.Serializer):
    """The account sources (null: not connected)."""

    lastfm = SettingsImportAccountSerializer(allow_null=True)
    koito = SettingsImportAccountSerializer(allow_null=True)
    xbox = SettingsImportAccountSerializer(allow_null=True)
    psn = SettingsImportAccountSerializer(allow_null=True)
    pocketcasts = SettingsImportAccountSerializer(allow_null=True)
    gpodder = SettingsImportAccountSerializer(allow_null=True)
    stremio = SettingsImportAccountSerializer(allow_null=True)
    audiobookshelf = SettingsImportAccountSerializer(allow_null=True)
    storyteller = SettingsImportAccountSerializer(allow_null=True)
    koreader = SettingsImportAccountSerializer(allow_null=True)


class SettingsImportSourceSerializer(serializers.Serializer):
    """A source's name and logo."""

    key = serializers.CharField(allow_blank=True)
    name = serializers.CharField(allow_blank=True)
    logo = serializers.CharField(allow_blank=True)


class SettingsImportScheduleSerializer(serializers.Serializer):
    """A periodic import."""

    task_name = serializers.CharField()
    source = SettingsImportSourceSerializer()
    schedule = serializers.CharField(allow_blank=True)
    username = serializers.CharField(allow_blank=True)
    mode = serializers.CharField(allow_blank=True)
    last_run = serializers.DateTimeField(allow_null=True)
    next_run = serializers.DateTimeField(allow_null=True)


class SettingsImportResultSerializer(serializers.Serializer):
    """An import task from the last 7 days."""

    source = SettingsImportSourceSerializer()
    date = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField(allow_blank=True)
    summary = serializers.CharField(allow_blank=True)
    errors = serializers.CharField(allow_blank=True)
    progress_current = serializers.IntegerField()
    progress_total = serializers.IntegerField()
    progress_label = serializers.CharField(allow_blank=True)
    progress_percent = serializers.FloatField()


class SettingsImportRunSerializer(serializers.Serializer):
    """A tracked import run (cancel while running, undo after)."""

    id = serializers.IntegerField()
    source = SettingsImportSourceSerializer()
    status = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    created = serializers.IntegerField()
    updated = serializers.IntegerField()
    skipped = serializers.IntegerField()
    failed = serializers.IntegerField()
    remaining = serializers.IntegerField(allow_null=True)
    cancel_url = serializers.CharField()
    rollback_url = serializers.CharField()


class SettingsImportSourceMediaSerializer(serializers.Serializer):
    """Items of one media type imported from one source."""

    media_type = serializers.CharField()
    source = SettingsImportSourceSerializer()
    count = serializers.IntegerField()
    delete_url = serializers.CharField()


class SettingsImportActivitySerializer(serializers.Serializer):
    """The Import page's activity panel (import_data_activity as JSON)."""

    schedules = SettingsImportScheduleSerializer(many=True)
    results = SettingsImportResultSerializer(many=True)
    runs = SettingsImportRunSerializer(many=True)
    source_media = SettingsImportSourceMediaSerializer(many=True)
    delete_schedule_url = serializers.CharField()


class SettingsImportSerializer(serializers.Serializer):
    """Import: settings, tiles, and the web sources' state."""

    is_demo = serializers.BooleanField()
    settings = SettingsImportSettingsSerializer()
    media_tags = SettingsImportTagSerializer(many=True)
    tiles = SettingsImportTileSerializer(many=True)
    mdblist_connected = serializers.BooleanField()
    hardcover_key_saved = serializers.BooleanField()
    trakt = SettingsImportTraktSerializer()
    lastfm_poll_interval = serializers.IntegerField()
    lastfm_recurring_every = serializers.IntegerField(allow_null=True)
    audiobookshelf_poll_interval = serializers.IntegerField()
    accounts = SettingsImportAccountsSerializer()
    plex = SettingsImportPlexSerializer(allow_null=True)
    radarr = SettingsImportArrSerializer(many=True)
    sonarr = SettingsImportArrSerializer(many=True)
    storyteller_pending = SettingsImportStorytellerPendingSerializer(allow_null=True)
    koreader = SettingsImportKoreaderSerializer(allow_null=True)
    activity = SettingsImportActivitySerializer(allow_null=True)
    urls = SettingsImportUrlsSerializer()
