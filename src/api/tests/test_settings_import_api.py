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
        self.assertFalse(tiles["plex"]["web"])
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

