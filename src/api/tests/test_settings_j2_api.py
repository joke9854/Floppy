"""Settings Preferences, Metadata, Export, Advanced, Connected apps (v2 P4-J2).

The web reads each page from GET /api/v1/settings/screen/<page>/ and posts
the Django forms with Accept: application/json. Preferences round-trips:
the screen's values posted back change nothing.
"""

import json
import tempfile
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import Item, MediaTypes, Movie, Sources
from app.providers import credentials
from users.models import CineTrackCrashReport

JSON = {"HTTP_ACCEPT": "application/json"}
REGIONS = [("UNSET", "Not set"), ("", "Disabled"), ("GB", "United Kingdom"), ("US", "United States")]
LANGUAGES = [("", "Server Default"), ("de-DE", "German"), ("en-US", "English")]


def _tmdb_lists(test):
    """Patch the two TMDB choice lists the Preferences page loads."""
    regions = mock.patch("users.views.tmdb.watch_provider_regions", return_value=REGIONS)
    languages = mock.patch("users.views.tmdb.metadata_languages", return_value=LANGUAGES)
    regions.start()
    languages.start()
    test.addCleanup(regions.stop)
    test.addCleanup(languages.stop)


class SettingsJ2Base(TestCase):
    def setUp(self):
        self.credentials = {"username": "j2", "password": "j2-password-1"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        backup_dir = tempfile.TemporaryDirectory()
        self.addCleanup(backup_dir.cleanup)
        backups = override_settings(BACKUP_DIR=backup_dir.name)
        backups.enable()
        self.addCleanup(backups.disable)

    def _screen(self, page):
        response = self.client.get(reverse("api_settings_screen", args=[page]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()


class PreferencesScreenTests(SettingsJ2Base):
    FIELDS = (
        "date_format",
        "time_format",
        "mobile_grid_layout",
        "media_card_subtitle_display",
        "progress_bar",
        "title_display_preference",
        "top_talent_sort_by",
        "watch_provider_region",
        "metadata_language",
        "ui_language",
        "hide_completed_recommendations",
        "rating_scale",
        "hide_zero_rating",
        "obfuscate_episodes",
        "hide_episode_overviews",
        "quick_season_update_mobile",
        "game_logging_style",
        "book_comic_manga_progress_percentage",
        "session_duration",
        "scrobble_watched_percent",
        "auto_pause_in_progress_enabled",
        "auto_pause_rules",
    )

    def _row(self):
        self.user.refresh_from_db()
        return {field: getattr(self.user, field) for field in self.FIELDS}

    def _post_back(self, preferences, **overrides):
        rules = preferences["auto_pause_rules"]
        data = {
            **preferences["values"],
            "auto_pause_enabled": "1" if rules else "0",
            "auto_pause_rules": json.dumps(rules),
            **overrides,
        }
        return self.client.post(preferences["save_url"], data, **JSON)

    def test_round_trip_changes_nothing(self):
        _tmdb_lists(self)
        # Start away from the defaults, or a reset would go unnoticed.
        self.user.date_format = "iso_8601"
        self.user.rating_scale = "5"
        self.user.progress_bar = False
        self.user.obfuscate_episodes = True
        self.user.session_duration = 604800
        self.user.scrobble_watched_percent = 75
        self.user.watch_provider_region = "GB"
        self.user.metadata_language = "de-DE"
        self.user.book_comic_manga_progress_percentage = True
        self.user.auto_pause_in_progress_enabled = True
        self.user.auto_pause_rules = [{"library": "all", "weeks": 8}]
        self.user.save()
        before = self._row()

        preferences = self._screen("preferences")["preferences"]
        names = {field["name"] for section in preferences["sections"] for field in section["fields"]}
        self.assertEqual(names, set(preferences["values"]))
        self.assertTrue(preferences["tmdb_lists_loaded"])
        self.assertEqual(preferences["values"]["watch_provider_region"], "GB")
        self.assertEqual(preferences["values"]["rating_scale"], "5")

        response = self._post_back(preferences)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["saved"])
        self.assertEqual(self._row(), before)

    def test_a_stored_value_the_list_lacks_still_shows(self):
        _tmdb_lists(self)
        self.user.watch_provider_region = "UNSET"
        self.user.save()
        with mock.patch("users.views.tmdb.watch_provider_regions", return_value=REGIONS[1:]):
            preferences = self._screen("preferences")["preferences"]
            region = preferences["sections"][1]["fields"][0]
            self.assertEqual(region["choices"][0], {"value": "UNSET", "label": "Not set", "hint": ""})
            self._post_back(preferences)
        self.assertEqual(self._row()["watch_provider_region"], "UNSET")

    def test_a_change_saves(self):
        _tmdb_lists(self)
        preferences = self._screen("preferences")["preferences"]
        response = self._post_back(
            preferences,
            watch_provider_region="US",
            obfuscate_episodes="1",
            auto_pause_enabled="1",
            auto_pause_rules=json.dumps([{"library": "all", "weeks": 3}]),
        )
        self.assertTrue(response.json()["saved"])
        row = self._row()
        self.assertEqual(row["watch_provider_region"], "US")
        self.assertTrue(row["obfuscate_episodes"])
        self.assertEqual(row["auto_pause_rules"], [{"library": "all", "weeks": 3}])

    def test_tmdb_down_keeps_region_and_language(self):
        self.user.watch_provider_region = "GB"
        self.user.metadata_language = "de-DE"
        self.user.save()
        with (
            mock.patch("users.views.tmdb.watch_provider_regions", side_effect=RuntimeError("down")),
            mock.patch("users.views.tmdb.metadata_languages", side_effect=RuntimeError("down")),
        ):
            preferences = self._screen("preferences")["preferences"]
            self.assertFalse(preferences["tmdb_lists_loaded"])
            self._post_back(preferences, watch_provider_region="US", metadata_language="en-US")
        row = self._row()
        self.assertEqual((row["watch_provider_region"], row["metadata_language"]), ("GB", "de-DE"))

    def test_get_still_renders_the_page(self):
        _tmdb_lists(self)
        response = self.client.get(reverse("preferences"), **JSON)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response["Content-Type"])

    def test_demo_is_refused(self):
        _tmdb_lists(self)
        self.user.is_demo = True
        self.user.save()
        response = self._post_back(self._screen("preferences")["preferences"])
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["saved"])


class MetadataScreenTests(SettingsJ2Base):
    def test_screen_never_returns_a_personal_key(self):
        credentials.set_user("tmdb", self.user, {"api_key": "personal-secret-9876"})
        response = self.client.get(reverse("api_settings_screen", args=["metadata"]))
        self.assertNotIn(b"personal-secret", response.content)
        self.assertNotIn(b"9876", response.content)
        metadata = response.json()["metadata"]
        self.assertFalse(metadata["can_edit_instance"])
        self.assertIsNotNone(metadata["promote"])
        providers = {p["slug"]: p for group in metadata["groups"] for p in group["providers"]}
        self.assertTrue(providers["tmdb"]["fields"][0]["has_personal_value"])

    def test_personal_key_save_and_remove(self):
        tmdb = {p["slug"]: p for g in self._screen("metadata")["metadata"]["groups"] for p in g["providers"]}["tmdb"]
        with mock.patch("app.providers.credentials._probe", return_value=None):
            saved = self.client.post(tmdb["urls"]["personal"], {"api_key": "personal-key-1"}, **JSON)
        self.assertEqual(saved.status_code, 200)
        self.assertTrue(saved.json()["saved"])
        self.assertTrue(credentials.has_user_value("tmdb", self.user))
        removed = self.client.post(tmdb["urls"]["personal"], {"api_key": ""}, **JSON)
        self.assertTrue(removed.json()["saved"])
        credentials.invalidate_user_cache(self.user)
        self.assertFalse(credentials.has_user_value("tmdb", self.user))

    def test_instance_save_is_refused_for_a_non_superuser(self):
        response = self.client.post(reverse("save_provider_credential", args=["tmdb"]), {"api_key": "x"}, **JSON)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["saved"])

    def test_unavailable_provider_is_refused(self):
        response = self.client.post(reverse("set_media_type_provider", args=["tv"]), {"source": "nope"}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertIn("isn't available", response.json()["error"])


class MetadataSuperuserTests(SettingsJ2Base):
    """Instance keys: a blank field deletes, an environment value is never overwritten."""

    def setUp(self):
        super().setUp()
        self.user.is_superuser = True
        self.user.save()
        probe = mock.patch("app.providers.credentials._probe", return_value=None)
        probe.start()
        self.addCleanup(probe.stop)

    def _tmdb(self):
        metadata = self._screen("metadata")["metadata"]
        self.assertTrue(metadata["can_edit_instance"])
        self.assertIsNone(metadata["promote"])
        return {p["slug"]: p for g in metadata["groups"] for p in g["providers"]}["tmdb"]

    @override_settings(TMDB_API="")
    def test_instance_key_save_and_clear(self):
        tmdb = self._tmdb()
        saved = self.client.post(tmdb["urls"]["save"], {"api_key": "instance-key-5678"}, **JSON)
        self.assertTrue(saved.json()["saved"])
        self.assertEqual(credentials.instance_value("tmdb", "api_key"), "instance-key-5678")
        response = self.client.get(reverse("api_settings_screen", args=["metadata"]))
        self.assertNotIn(b"instance-key", response.content)
        field = {p["slug"]: p for g in response.json()["metadata"]["groups"] for p in g["providers"]}["tmdb"]["fields"][0]
        self.assertTrue(field["has_instance_value"])
        self.assertTrue(field["preview"].endswith("5678"))

        cleared = self.client.post(tmdb["urls"]["clear"], **JSON)
        self.assertTrue(cleared.json()["saved"])
        credentials.invalidate_cache()
        self.assertFalse(credentials.instance_value("tmdb", "api_key"))

    @override_settings(TMDB_API="environment-key-1")
    def test_an_environment_value_is_never_overwritten(self):
        tmdb = self._tmdb()
        self.assertTrue(tmdb["fields"][0]["locked"])
        self.client.post(tmdb["urls"]["save"], {"api_key": "posted-anyway"}, **JSON)
        self.assertFalse(credentials.instance_value("tmdb", "api_key"))


class AnimePromptTests(SettingsJ2Base):
    """The conversion prompt comes back in the POST answer, not the session."""

    def test_provider_change_returns_the_count(self):
        from app.services import metadata_resolution

        sources = [source.value for source in metadata_resolution.available_metadata_sources("anime")]
        current = metadata_resolution.metadata_default_source(self.user, "anime")
        other = next((source for source in sources if source != current), None)
        if other is None:
            self.skipTest("only one anime source is configured here")
        with mock.patch(
            "app.tasks_anime_library_repair.anime_rows_needing_conversion", return_value=[object(), object()]
        ):
            response = self.client.post(reverse("set_media_type_provider", args=["anime"]), {"source": other}, **JSON)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response.json()["anime_shape_prompt_count"], 2)
        self.assertNotIn("anime_shape_prompt_count", self.client.session)

    def test_convert_answers_json(self):
        with mock.patch("app.tasks_anime_library_repair.convert_anime_library_shape_task.delay") as delay:
            response = self.client.post(reverse("convert_anime_library"), **JSON)
        self.assertTrue(response.json()["saved"])
        delay.assert_called_once_with(self.user.id)


class ExportScreenTests(SettingsJ2Base):
    def test_screen(self):
        export = self._screen("export")["export"]
        self.assertIn("movie", [row["value"] for row in export["media_types"]])
        self.assertNotIn("episode", [row["value"] for row in export["media_types"]])
        self.assertEqual(export["schedules"], [])
        self.assertEqual(export["backup"]["file_count"], 0)

    def test_export_errors_answer_json_and_success_is_the_csv(self):
        url = self._screen("export")["export"]["urls"]["export"]
        empty = self.client.post(url, {"frequency": "once"}, **JSON)
        self.assertEqual(empty.status_code, 400)
        self.assertIn("Select at least one", empty.json()["error"])
        csv = self.client.post(url, {"frequency": "once", "include_lists": "on"}, **JSON)
        self.assertEqual(csv.status_code, 200)
        self.assertEqual(csv["Content-Type"], "text/csv")

    def test_deleting_a_missing_schedule_fails(self):
        url = self._screen("export")["export"]["urls"]["delete_schedule"]
        response = self.client.post(url, {"task_name": "nope"}, **JSON)
        self.assertEqual(response.status_code, 400)


class AdvancedScreenTests(SettingsJ2Base):
    def test_proxy_is_never_returned(self):
        advanced = self._screen("advanced")["advanced"]
        self.assertFalse(advanced["tmdb_proxy_configured"])
        saved = self.client.post(advanced["urls"]["tmdb_proxy"], {"tmdb_proxy_url": "socks5://u:pw@proxy:1080"}, **JSON)
        self.assertTrue(saved.json()["saved"])
        response = self.client.get(reverse("api_settings_screen", args=["advanced"]))
        self.assertNotIn(b"proxy:1080", response.content)
        self.assertTrue(response.json()["advanced"]["tmdb_proxy_configured"])
        self.client.post(advanced["urls"]["tmdb_proxy"], {"tmdb_proxy_url": ""}, **JSON)
        self.assertFalse(self._screen("advanced")["advanced"]["tmdb_proxy_configured"])

    def test_superuser_only_forms_refuse(self):
        advanced = self._screen("advanced")["advanced"]
        self.assertFalse(advanced["is_superuser"])
        response = self.client.post(advanced["urls"]["image_cache"], {"image_caching_enabled": "1"}, **JSON)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json()["saved"])

    def test_clear_a_cache(self):
        history = {cache["key"]: cache for cache in self._screen("advanced")["advanced"]["caches"]}["history"]
        response = self.client.post(history["url"], **JSON)
        self.assertTrue(response.json()["saved"])
        self.assertIn("history cache", response.json()["message"])

    def test_delete_a_media_type(self):
        item = Item.objects.create(
            media_id="j2-1", source=Sources.MANUAL.value, media_type=MediaTypes.MOVIE.value, title="Low Tide"
        )
        Movie.objects.create(item=item, user=self.user)
        url = self._screen("advanced")["advanced"]["urls"]["delete_media_type"]
        response = self.client.post(url, {"media_type": "movie", "delete_metadata": "false"}, **JSON)
        self.assertTrue(response.json()["saved"])
        self.assertIn("Permanently deleted 1", response.json()["message"])
        self.assertFalse(Movie.objects.filter(user=self.user).exists())


class ConnectedAppsScreenTests(SettingsJ2Base):
    def test_screen(self):
        CineTrackCrashReport.objects.create(
            user=self.user,
            report_id=uuid.uuid4(),
            kind="crash",
            occurred_at=timezone.now(),
            app_version="0.99.80",
            version_code=1,
            build_type="release",
            android_sdk=35,
            device_model="Test phone",
            exception_class="java.lang.IllegalStateException",
            stack_trace="at test",
        )
        apps = self._screen("connected-apps")["connected_apps"]
        self.assertEqual(apps["sessions"], [])
        self.assertEqual(apps["crash_report_count"], 1)
        self.assertEqual(apps["crash_reports"][0]["kind"], "Crash")
        self.assertEqual(apps["urls"]["integrations"], reverse("integrations"))

    def test_revoking_an_unknown_session_is_404(self):
        response = self.client.post(reverse("revoke_app_session", args=["r999999"]), **JSON)
        self.assertEqual(response.status_code, 404)
