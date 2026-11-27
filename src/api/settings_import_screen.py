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

# Sources the web draws (K1); the rest open the Django page's dialog.
WEB_SOURCES = frozenset(
    {
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
        },
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
    """Import: settings, tiles, and the K1 sources' state."""

    is_demo = serializers.BooleanField()
    settings = SettingsImportSettingsSerializer()
    media_tags = SettingsImportTagSerializer(many=True)
    tiles = SettingsImportTileSerializer(many=True)
    mdblist_connected = serializers.BooleanField()
    hardcover_key_saved = serializers.BooleanField()
    activity = SettingsImportActivitySerializer(allow_null=True)
    urls = SettingsImportUrlsSerializer()
