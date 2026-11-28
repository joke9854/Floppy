"""Settings > Import for the web (v2 P4-K1).

The screen lists the source tiles (the web draws the K1 dialogs, the rest
open the Django page), the import settings and the activity panel. The
import forms answer JSON for the web.
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from api.settings_import_screen import WEB_SOURCES

JSON = {"HTTP_ACCEPT": "application/json"}
SHARED = {"frequency": "once", "time": "00:00", "mode": "new"}


class ImportScreenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="k1", password="k1-password-1")
        self.client.login(username="k1", password="k1-password-1")

    def _screen(self):
        response = self.client.get(reverse("api_settings_screen", args=["import"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        body = response.json()
        self.assertTrue(body["handled"])
        return body["import_"]

    def test_screen_tiles_and_settings(self):
        screen = self._screen()
        tiles = {tile["key"]: tile for tile in screen["tiles"]}
        self.assertEqual({key for key, tile in tiles.items() if tile["web"]}, set(WEB_SOURCES))
        self.assertTrue(tiles["plex"]["web"])
        self.assertEqual(tiles["plex"]["django_url"], reverse("import_data") + "?open=plex")
        self.assertEqual(screen["settings"]["frequency"], self.user.import_frequency)
        self.assertEqual(screen["media_tags"][0]["value"], "all")
        self.assertEqual(screen["activity"]["schedules"], [])

    def test_settings_save_keeps_missing_fields(self):
        url = self._screen()["settings"]["save_url"]
        response = self.client.post(url, {"import_frequency": "daily", "import_time": "04:30", "import_mode": "overwrite"}, **JSON)
        self.assertEqual(response.status_code, 204)
        self.client.post(url, {"import_mode": "new"}, **JSON)
        self.user.refresh_from_db()
        self.assertEqual((self.user.import_frequency, self.user.import_time, self.user.import_mode), ("daily", "04:30", "new"))

    def test_activity_answers_json(self):
        url = self._screen()["urls"]["activity"]
        activity = self.client.get(url, **JSON).json()
        self.assertEqual(set(activity), {"schedules", "results", "runs", "source_media", "delete_schedule_url"})
        self.assertIn("text/html", self.client.get(url)["Content-Type"])

    def test_upload_without_a_file_fails(self):
        url = self._screen()["urls"]["yamtrack"]
        response = self.client.post(url, SHARED, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "A CSV file is required.")

    def test_upload_is_queued(self):
        url = self._screen()["urls"]["hltb"]
        upload = SimpleUploadedFile("games.csv", b"Title\nPortal\n", content_type="text/csv")
        with mock.patch("integrations.views.tasks.import_hltb.delay") as delay:
            response = self.client.post(url, {**SHARED, "hltb_csv": upload}, **JSON)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["saved"])
        self.assertIn("has been queued", response.json()["message"])
        delay.assert_called_once()

    def test_username_import_once_and_missing(self):
        url = self._screen()["urls"]["mal"]
        missing = self.client.post(url, SHARED, **JSON)
        self.assertEqual(missing.json()["error"], "MyAnimeList username is required.")
        with mock.patch("integrations.views.tasks.import_mal.delay") as delay:
            queued = self.client.post(url, {**SHARED, "user": "someone"}, **JSON)
        self.assertTrue(queued.json()["saved"])
        delay.assert_called_once_with(username="someone", user_id=self.user.id, mode="new")

    def test_hardcover_needs_a_key_or_a_file(self):
        url = self._screen()["urls"]["hardcover"]
        response = self.client.post(url, SHARED, **JSON)
        self.assertEqual(response.status_code, 400)

    def test_run_actions_refuse_unknown_ids(self):
        self.assertEqual(self.client.post(reverse("cancel_import_run", args=[999999]), **JSON).status_code, 404)
        missing = self.client.post(reverse("delete_import_schedule"), {"task_name": "nope"}, **JSON)
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()["error"], "Import schedule not found.")

    def test_screen_opens_when_activity_fails(self):
        with mock.patch("users.models.User.get_import_tasks", side_effect=ConnectionError("result store down")):
            screen = self._screen()
        self.assertIsNone(screen["activity"])


class ImportK2Tests(TestCase):
    """K2: account-based sources (connect, sync, history, disconnect) answer JSON."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="k2", password="k2-password-1")
        self.client.login(username="k2", password="k2-password-1")

    def _screen(self):
        response = self.client.get(reverse("api_settings_screen", args=["import"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response

    def test_screen_without_accounts(self):
        screen = self._screen().json()["import_"]
        tiles = {tile["key"]: tile["web"] for tile in screen["tiles"]}
        for key in ("trakt", "anilist", "lastfm", "koito", "steam", "xbox", "psn", "pocketcasts", "gpodder"):
            self.assertTrue(tiles[key], key)
        self.assertEqual(set(screen["accounts"].values()), {None})
        self.assertEqual(screen["lastfm_poll_interval"], 15)
        self.assertIsNone(screen["lastfm_recurring_every"])
        # The test client is plain http on a non-loopback host: Trakt's device flow.
        self.assertFalse(screen["trakt"]["redirect_capable"])
        self.assertEqual(screen["trakt"]["redirect_uri"], "urn:ietf:wg:oauth:2.0:oob")

    def test_screen_accounts_never_carry_secrets(self):
        from integrations.models import (
            GPodderAccount,
            KoitoAccount,
            LastFMAccount,
            PocketCastsAccount,
            PSNAccount,
            XboxAccount,
        )

        LastFMAccount.objects.create(
            user=self.user,
            lastfm_username="listener",
            history_import_status="failed",
            history_import_last_error_message="rate limited",
            history_import_total_pages=10,
            history_import_next_page=4,
        )
        KoitoAccount.objects.create(
            user=self.user, base_url="http://koito.test", api_key="koito-secret-1", connection_broken=True, last_error_message="bad key"
        )
        XboxAccount.objects.create(user=self.user, api_key="xbox-secret-1", gamertag="Player One")
        PSNAccount.objects.create(user=self.user, npsso="psn-secret-1", online_id="player_one")
        PocketCastsAccount.objects.create(
            user=self.user, email="pc@example.test", password="pc-secret-1", access_token="pc-token-1", refresh_token="pc-refresh-1"
        )
        GPodderAccount.objects.create(user=self.user, server_url="http://gpodder.test", username="gp-user", password="gp-secret-1")
        response = self._screen()
        for secret in (b"koito-secret-1", b"xbox-secret-1", b"psn-secret-1", b"pc-secret-1", b"pc-token-1", b"pc-refresh-1", b"gp-secret-1", b"pc@example.test"):
            self.assertNotIn(secret, response.content)
        accounts = response.json()["import_"]["accounts"]
        lastfm = accounts["lastfm"]["history"]
        self.assertEqual((lastfm["label"], lastfm["current_page"], lastfm["total_pages"]), ("Failed", 4, 10))
        self.assertEqual((lastfm["error"], lastfm["button"], lastfm["can_start"]), ("rate limited", "Reimport full history", True))
        self.assertEqual(accounts["koito"]["name"], "http://koito.test")
        self.assertEqual(accounts["koito"]["error"], "bad key")
        self.assertEqual(accounts["xbox"]["name"], "Player One")
        self.assertEqual(accounts["psn"]["name"], "player_one")
        self.assertIsNone(accounts["pocketcasts"]["history"])

    def test_connect_errors_answer_json(self):
        urls = self._screen().json()["import_"]["urls"]
        cases = {
            "lastfm_connect": ({}, "Last.fm username is required."),
            "koito_connect": ({}, "Koito server URL and API key are required."),
            "xbox_connect": ({}, "An OpenXBL API key is required."),
            "psn_connect": ({}, "A PSN NPSSO token is required."),
            "pocketcasts_connect": ({"password": "x"}, "Email is required."),
            "gpodder_connect": ({"server_url": "http://gpodder.test", "password": "x"}, "Username is required."),
        }
        for key, (fields, error) in cases.items():
            response = self.client.post(urls[key], fields, **JSON)
            self.assertEqual(response.status_code, 400, key)
            self.assertEqual(response.json()["error"], error, key)

    def test_actions_without_an_account_answer_json(self):
        urls = self._screen().json()["import_"]["urls"]
        for key in ("lastfm_sync", "lastfm_history", "koito_sync", "koito_history", "xbox_sync", "psn_sync", "pocketcasts_sync", "gpodder_sync"):
            response = self.client.post(urls[key], SHARED, **JSON)
            self.assertEqual(response.status_code, 400, key)
            self.assertTrue(response.json()["error"], key)
        for key in ("lastfm_disconnect", "koito_disconnect", "xbox_disconnect", "psn_disconnect", "pocketcasts_disconnect", "gpodder_disconnect"):
            response = self.client.post(urls[key], **JSON)
            self.assertEqual(response.status_code, 200, key)
            self.assertTrue(response.json()["saved"], key)

    def test_koito_connect_queues(self):
        url = self._screen().json()["import_"]["urls"]["koito_connect"]
        with mock.patch("integrations.views.connections.connect_koito") as connect:
            response = self.client.post(url, {"base_url": "http://koito.test", "api_key": "k"}, **JSON)
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["saved"])
        connect.assert_called_once()

    def test_username_imports_queue(self):
        urls = self._screen().json()["import_"]["urls"]
        for key, task in (("trakt_public", "import_trakt"), ("anilist_public", "import_anilist"), ("steam", "import_steam")):
            with mock.patch(f"integrations.views.tasks.{task}.delay") as delay:
                response = self.client.post(urls[key], {**SHARED, "user": "someone"}, **JSON)
            self.assertEqual(response.status_code, 200, (key, response.content[:300]))
            self.assertTrue(response.json()["saved"], key)
            delay.assert_called_once()
            missing = self.client.post(urls[key], SHARED, **JSON)
            self.assertEqual(missing.status_code, 400, key)

    def test_trakt_export_needs_a_file(self):
        url = self._screen().json()["import_"]["urls"]["trakt_export"]
        response = self.client.post(url, {"mode": "new"}, **JSON)
        self.assertEqual(response.json()["error"], "A Trakt export file is required.")

    def test_oauth_starts_stay_redirects(self):
        url = self._screen().json()["import_"]["urls"]["anilist_oauth"]
        response = self.client.post(url, {**SHARED, "next": "/next/settings/import"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("https://anilist.co/"))


class ImportK3Tests(TestCase):
    """K3: media servers and readers (Plex, Radarr, Sonarr, Stremio, Audiobookshelf, Storyteller, KOReader)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="k3", password="k3-password-1")
        self.client.login(username="k3", password="k3-password-1")

    def _screen(self):
        response = self.client.get(reverse("api_settings_screen", args=["import"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response

    def test_every_tile_is_web(self):
        screen = self._screen().json()["import_"]
        self.assertTrue(all(tile["web"] for tile in screen["tiles"]))
        self.assertIsNone(screen["plex"])
        self.assertEqual((screen["radarr"], screen["sonarr"]), ([], []))
        self.assertIsNone(screen["storyteller_pending"])
        self.assertIsNone(screen["koreader"])
        self.assertEqual(screen["audiobookshelf_poll_interval"], 15)

    def test_screen_never_carries_secrets(self):
        from integrations.models import (
            AudiobookshelfAccount,
            KoreaderAccount,
            PlexAccount,
            RadarrInstance,
            StorytellerAccount,
            StremioAccount,
        )

        PlexAccount.objects.create(
            user=self.user,
            plex_token="plex-secret-1",
            plex_username="viewer",
            sections=[
                {
                    "id": "1",
                    "title": "Films",
                    "type": "movie",
                    "server_name": "Home",
                    "machine_identifier": "abc",
                    "uri": "http://plex-secret-uri.test:32400",
                    "access_token": "plex-section-secret-1",
                }
            ],
        )
        RadarrInstance.objects.create(user=self.user, name="4K", base_url="http://radarr.test", api_key="radarr-secret-1")
        StremioAccount.objects.create(user=self.user, auth_key="stremio-secret-1", email="stremio@example.test")
        AudiobookshelfAccount.objects.create(user=self.user, base_url="http://abs.test", api_token="abs-secret-1")
        StorytellerAccount.objects.create(user=self.user, server_url="http://storyteller.test", auth_token="st-secret-1")
        KoreaderAccount.objects.create(
            user=self.user, server_url="http://kosync.test", username="reader", auth_key="ko-secret-1", finished_threshold=0.95
        )
        session = self.client.session
        session["storyteller_pending_auth"] = {"device_code": "device-secret-1", "user_code": "ABCD", "verification_uri": "http://st.test/a"}
        session.save()
        response = self._screen()
        for secret in (
            b"plex-secret-1",
            b"plex-secret-uri",
            b"plex-section-secret-1",
            b"radarr-secret-1",
            b"stremio-secret-1",
            b"stremio@example.test",
            b"abs-secret-1",
            b"st-secret-1",
            b"ko-secret-1",
            b"device-secret-1",
        ):
            self.assertNotIn(secret, response.content)
        screen = response.json()["import_"]
        self.assertEqual(screen["plex"]["libraries"][0]["value"], "abc::1")
        self.assertEqual(screen["plex"]["libraries"][0]["label"], "Films - Home (Movie)")
        self.assertEqual(screen["radarr"][0]["name"], "4K")
        self.assertEqual(screen["storyteller_pending"]["user_code"], "ABCD")
        self.assertEqual(screen["koreader"]["finished_threshold_percent"], 95)
        self.assertEqual(screen["accounts"]["audiobookshelf"]["name"], "http://abs.test")

        sections = self.client.get(screen["urls"]["plex_sections"])
        self.assertEqual(sections.status_code, 200)
        self.assertNotIn(b"plex-section-secret-1", sections.content)
        self.assertNotIn(b"plex-secret-uri", sections.content)

    def test_errors_answer_json(self):
        urls = self._screen().json()["import_"]["urls"]
        cases = {
            "radarr_connect": ({}, "Radarr base URL and API key are required."),
            "stremio_connect": ({}, "Enter your Stremio email and password, or an auth key."),
            "audiobookshelf_connect": ({}, "Audiobookshelf base URL and API token are required."),
            "storyteller_connect": ({}, "Storyteller server URL is required."),
            "koreader_connect": (SHARED, "Server URL, username, and password are required."),
            "koreader_settings": ({}, "Connect KOReader before changing settings."),
            "plex_import": (SHARED, "Connect Plex before importing."),
            "plex_disable_watchlist": ({}, "Connect Plex before changing watchlist sync."),
            "stremio_sync": ({}, "Connect Stremio before importing."),
            "audiobookshelf_sync": ({}, "Connect Audiobookshelf before importing."),
            "storyteller_sync": ({}, "Connect Storyteller before importing."),
            "koreader_sync": (SHARED, "Connect KOReader before importing."),
        }
        for key, (fields, error) in cases.items():
            response = self.client.post(urls[key], fields, **JSON)
            self.assertEqual(response.status_code, 400, key)
            self.assertEqual(response.json()["error"], error, key)
        self.assertEqual(self.client.post(urls["radarr_sync"], {"instance_id": "999999"}, **JSON).status_code, 404)
        cancel = self.client.post(urls["storyteller_cancel"], **JSON)
        self.assertTrue(cancel.json()["saved"])

    def test_radarr_connect_and_sync(self):
        urls = self._screen().json()["import_"]["urls"]
        with mock.patch("integrations.views.connections.connect_radarr") as connect:
            response = self.client.post(urls["radarr_connect"], {"base_url": "http://radarr.test", "api_key": "k"}, **JSON)
        self.assertTrue(response.json()["saved"], response.content[:300])
        connect.assert_called_once()

    def test_plex_connect_from_the_web_skips_the_first_import(self):
        url = self._screen().json()["import_"]["urls"]["plex_connect"]
        with mock.patch("integrations.views.plex_api.create_pin", return_value={"id": 1, "code": "pin"}):
            response = self.client.post(url, {"next": "/next/settings/import", "auto_import": "0"})
        self.assertEqual(response.status_code, 302)
        states = [value for value in self.client.session.values() if isinstance(value, dict) and "plex_pin_id" in value]
        self.assertEqual([(state["return_to"], state["auto_import"]) for state in states], [("/next/settings/import", False)])

