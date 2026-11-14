"""FLOPPY_BETA_MODE: run a second instance on a copy of real data safely.

A beta instance works on a copy of the production database. That copy still
holds every connected service's credentials and per-user schedules, so a beta
instance that kept running them would double-push watched states, send
duplicate notifications and rotate single-use OAuth refresh tokens (Trakt
tokens live in PeriodicTask kwargs, Pocket Casts logs in with a stored
password), which would break the real instance.

Anything that contacts a service the user connected is therefore blocked here.
Read-only metadata providers that use a static key (TMDB, TVDB, IGDB, fanart,
MAL/AniList public metadata, Trakt popularity) are untouched.

This module must stay cheap to import: Celery loads it before Django models
are available, so settings are read lazily and nothing here imports models.
"""

import logging

from celery import Task

logger = logging.getLogger(__name__)

BETA_SKIP_MESSAGE = "Skipped: beta server, connected services are paused."
BETA_BLOCKED_DETAIL = (
    "This is a beta server. It works on a copy of your data and does not "
    "contact connected services."
)

# Celery tasks that talk to a service the user connected, or send something to
# the user. Keyed by the registered task name.
BLOCKED_TASK_NAMES = frozenset(
    {
        # Watched-state sync with providers.
        "Push Watched State to Jellyfin",
        "Deliver watched state to a provider",
        "Sweep pending watched state deliveries",
        "Reconcile watched state with a provider",
        "Pull Jellyfin watch history",
        # Account imports (also covers public-username Trakt/AniList imports).
        "Import from Trakt",
        "Import from SIMKL",
        "Import from AniList",
        "Import from MDBList",
        "Import from Steam",
        "Import from Xbox",
        "Import from Xbox (Recurring)",
        "Import from PSN",
        "Import from PSN (Recurring)",
        "Import from Plex",
        "Sync Plex Watchlist",
        "Import from Radarr",
        "Import from Radarr (Recurring)",
        "Import from Sonarr",
        "Import from Sonarr (Recurring)",
        "Import from Audiobookshelf",
        "Import from Audiobookshelf (Recurring)",
        "Import from Storyteller",
        "Import from Storyteller (Recurring)",
        "Import from KOReader",
        "Import from Stremio",
        "Import from Stremio (Recurring)",
        "Import from Pocket Casts",
        "Import from Pocket Casts (Recurring)",
        "Import from GPodder",
        "Import from GPodder (Recurring)",
        # Scrobble polling.
        "Poll Last.fm for user",
        "Import from Last.fm History",
        "Poll Last.fm for all users",
        "Poll Koito for user",
        "Poll Koito for all users",
        "Import from Koito History",
        # Plex library and webhook handling.
        "Refresh Plex library sections",
        "Update collection metadata from Plex webhook",
        "Fetch collection metadata for item",
        "Update collection metadata from Plex",
        "Process media server webhook",
        "Process Stremio playback webhook",
        "Verify Stremio playback completion",
        # Lists backed by a connected account.
        "Import MDBList Lists",
        "Import MDBList List",
        "Import Trakt Lists",
        # Notifications to the user.
        "Send release notifications",
        "Send daily digest",
        "Send premiere digest",
    },
)

# Integration-area tasks that stay local or use a static, read-only client.
BETA_SAFE_TASK_NAMES = frozenset(
    {
        # File uploads.
        "Import from Yamtrack",
        "Import from CLZ",
        "Import from HowLongToBeat",
        "Import from Grouvee",
        "Import from Hardcover",
        "Import from IMDB",
        "Import from Goodreads",
        "Import from GoodReads",
        "integrations.tasks.import_goodreads",
        "Import from StoryGraph",
        "Import from TV Time (shows)",
        "Import from TV Time (movies)",
        "Import from Jellyfin Playback Reporting",
        "Import Trakt data export",
        "Import Trakt collection CSV",
        "Import List From CSV",
        # Public metadata with a static client.
        "Import from Kitsu",
        "Import from MyAnimeList",
        # Local-only work.
        "Scheduled backup export",
        "Sync Smart List Items",
        "Sync Smart Lists For Items",
        "integrations.compact_watch_state_changes",
        "integrations.compact_integration_event_receipts",
    },
)

# URL names of views that contact a connected service while handling the
# request (OAuth hand-offs, connection tests, manual pushes and pulls).
BLOCKED_URL_NAMES = frozenset(
    {
        # integrations
        "trakt_oauth",
        "import_trakt_private",  # Trakt OAuth callback (_finish_trakt_connection)
        "trakt_device_verify",
        "trakt_device_poll",
        "plex_connect",
        "plex_callback",
        "simkl_oauth",
        "import_anilist_oauth",
        "radarr_connect",
        "sonarr_connect",
        "jellyfin_connect",
        "jellyfin_push_now",
        "jellyfin_pull_now",
        "audiobookshelf_connect",
        "storyteller_connect",
        "storyteller_poll",
        "koreader_connect",
        "stremio_connect",
        "xbox_connect",
        "psn_connect",
        "pocketcasts_connect",
        "gpodder_connect",
        "lastfm_connect",
        "poll_lastfm_manual",
        "koito_connect",
        "poll_koito_manual",
        "import_plex",
        "import_simkl_private",
        "import_anilist_private",
        "import_steam",
        "import_pocketcasts",
        # lists
        "trakt_lists_oauth",
        "trakt_lists_device_verify",
        "trakt_lists_device_poll",
        "trakt_lists_callback",
        "mdblist_connect",
        "mdblist_sync_now",
        "mdblist_import_url",
        # users
        "test_notification",
        "import_data_plex_sections",
        "import_data_plex_status",
        # api
        "api_user_notification_test",
    },
)


def is_beta_mode() -> bool:
    """Return True when this instance is a beta copy."""
    from django.conf import settings

    return bool(getattr(settings, "FLOPPY_BETA_MODE", False))


def is_blocked_task(name) -> bool:
    """Return True when beta mode must not run the task called ``name``."""
    return is_beta_mode() and name in BLOCKED_TASK_NAMES


def is_blocked_url_name(url_name) -> bool:
    """Return True when beta mode must not serve the view named ``url_name``."""
    return is_beta_mode() and url_name in BLOCKED_URL_NAMES


class BetaGuardTask(Task):
    """Celery base task that skips blocked tasks on a beta instance."""

    def __call__(self, *args, **kwargs):
        """Skip the task body when beta mode blocks it."""
        if is_blocked_task(self.name):
            # Task name only: kwargs can hold tokens.
            logger.info("Beta server: skipped task %s", self.name)
            return BETA_SKIP_MESSAGE
        return super().__call__(*args, **kwargs)
