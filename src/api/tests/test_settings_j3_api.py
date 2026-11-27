"""Settings Integrations and RSS for the web (v2 P4-J3).

The screen carries the legacy key and URLs built on it, so it must answer the
browser session only, never an API token. The forms answer JSON for the web;
those that clear a missing field round-trip with the screen's values.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from integrations.models import CatalogGrant
from users import credentials as user_credentials

JSON = {"HTTP_ACCEPT": "application/json"}


class IntegrationsScreenTests(TestCase):
    def setUp(self):
        self.credentials = {"username": "j3", "password": "j3-password-1"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _screen(self, page="integrations"):
        response = self.client.get(reverse("api_settings_screen", args=[page]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_screen_carries_the_key_and_webhook_urls(self):
        screen = self._screen()
        self.assertTrue(screen["handled"])
        integrations = screen["integrations"]
        self.assertEqual(integrations["api"]["legacy_token"], self.user.token)
        for url in (
            integrations["plex"]["webhook_url"],
            integrations["jellyfin"]["webhook_url"],
            integrations["emby_webhook_url"],
            integrations["kodi_webhook_url"],
            integrations["seerr"]["webhook_url"],
            integrations["stremio"]["addon_url"],
        ):
            self.assertIn(self.user.token, url)
        self.assertEqual({card["key"] for card in integrations["cards"]} >= {"plex", "jellyfin", "trakt"}, True)

    def test_an_api_token_cannot_read_the_screen(self):
        _token, secret = user_credentials.create_integration_token(self.user, "probe", ["scrobble:write"])
        response = Client().get(
            reverse("api_settings_screen", args=["integrations"]), HTTP_AUTHORIZATION=f"Bearer {secret}"
        )
        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn(self.user.token.encode(), response.content)

    def test_create_token_answers_the_secret_once(self):
        url = self._screen()["integrations"]["api"]["create_token_url"]
        response = self.client.post(url, {"name": "Living room", "scopes": ["scrobble:write"]}, **JSON)
        self.assertEqual(response.status_code, 200, response.content[:300])
        new = response.json()["new_token"]
        self.assertEqual(new["name"], "Living room")
        self.assertTrue(new["secret"].startswith("flp_"))
        self.assertNotIn("new_integration_token", self.client.session)
        tokens = self._screen()["integrations"]["api"]["tokens"]
        self.assertEqual([token["name"] for token in tokens], ["Living room"])
        refused = self.client.post(url, {"name": "", "scopes": ["scrobble:write"]}, **JSON)
        self.assertEqual(refused.status_code, 400)

    def test_jellyfin_events_round_trip(self):
        self.user.jellyfin_mark_played_enabled = True
        self.user.jellyfin_mark_unplayed_enabled = False
        self.user.save()
        jellyfin = self._screen()["integrations"]["jellyfin"]
        data = {
            field: "on"
            for field, on in (
                ("jellyfin_mark_played_enabled", jellyfin["mark_played_enabled"]),
                ("jellyfin_mark_unplayed_enabled", jellyfin["mark_unplayed_enabled"]),
            )
            if on
        }
        self.assertTrue(self.client.post(jellyfin["urls"]["events"], data, **JSON).json()["saved"])
        self.user.refresh_from_db()
        self.assertEqual((self.user.jellyfin_mark_played_enabled, self.user.jellyfin_mark_unplayed_enabled), (True, False))

    def test_jellyfin_settings_need_a_connection(self):
        url = self._screen()["integrations"]["jellyfin"]["urls"]["settings"]
        response = self.client.post(url, {"push_watched_enabled": "on"}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Connect Jellyfin", response.json()["error"])

    def test_seerr_round_trip(self):
        self.user.jellyseerr_enabled = True
        self.user.jellyseerr_trigger_statuses = "PENDING,AVAILABLE"
        self.user.jellyseerr_allowed_usernames = "ana,bo"
        self.user.jellyseerr_default_added_status = "In progress"
        self.user.save()
        fields = (
            "jellyseerr_enabled",
            "jellyseerr_trigger_statuses",
            "jellyseerr_allowed_usernames",
            "jellyseerr_default_added_status",
        )
        before = {field: getattr(self.user, field) for field in fields}
        seerr = self._screen()["integrations"]["seerr"]
        response = self.client.post(
            seerr["save_url"],
            {
                "jellyseerr_enabled": "1" if seerr["enabled"] else "0",
                "jellyseerr_trigger_statuses": seerr["trigger_statuses"],
                "jellyseerr_allowed_usernames": seerr["allowed_usernames"],
                "jellyseerr_default_added_status": seerr["default_added_status"],
            },
            **JSON,
        )
        self.assertTrue(response.json()["saved"])
        self.user.refresh_from_db()
        self.assertEqual({field: getattr(self.user, field) for field in fields}, before)
        bad = self.client.post(seerr["save_url"], {"jellyseerr_trigger_statuses": "NOPE"}, **JSON)
        self.assertEqual(bad.status_code, 400)

    def test_plex_usernames_round_trip(self):
        self.user.plex_usernames = "ana, bo"
        self.user.save()
        plex = self._screen()["integrations"]["plex"]
        self.assertFalse(plex["connected"])
        response = self.client.post(plex["urls"]["usernames"], {"plex_usernames": plex["usernames"]}, **JSON)
        self.assertTrue(response.json()["saved"])
        self.user.refresh_from_db()
        self.assertEqual(self.user.plex_usernames, "ana, bo")

    def test_install_credentials(self):
        stremio = self._screen()["integrations"]["stremio"]
        created = self.client.post(
            stremio["create_grant_url"], {"name": "Living room TV", "allow_playback_start": "on"}, **JSON
        )
        self.assertTrue(created.json()["saved"])
        grant = CatalogGrant.objects.get(user=self.user)
        response = self.client.get(reverse("api_settings_screen", args=["integrations"]))
        stremio = response.json()["integrations"]["stremio"]
        # The newest install credential is the addon URL, as on the Django page.
        self.assertIn(grant.token, stremio["addon_url"])
        self.assertEqual([row["name"] for row in stremio["grants"]], ["Living room TV"])
        self.assertNotIn("token", stremio["grants"][0])
        revoked = self.client.post(stremio["grants"][0]["revoke_url"], **JSON)
        self.assertTrue(revoked.json()["saved"])

    def test_sync_and_match_refusals(self):
        sync = self._screen()["integrations"]["sync"]
        self.assertEqual(sync["bindings"], [])
        response = self.client.post(sync["urls"]["pause"], {"binding_id": "999999", "kill_switch": "on"}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(reverse("match_reference_status", args=[999999, "ignored"]), **JSON).status_code, 404)

    def test_regenerate_rotates_the_key(self):
        old = self.user.token
        url = self._screen()["integrations"]["api"]["regenerate_url"]
        self.assertTrue(self.client.post(url, **JSON).json()["saved"])
        self.assertNotEqual(self._screen()["integrations"]["api"]["legacy_token"], old)


class RssScreenTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="j3rss", password="j3-password-1")
        self.client.login(username="j3rss", password="j3-password-1")

    def test_screen_and_json_preview(self):
        rss = self.client.get(reverse("api_settings_screen", args=["rss"])).json()
        self.assertTrue(rss["handled"])
        body = rss["rss"]
        self.assertIn("MEDIA_TYPE_PLACEHOLDER", body["feed_url_template"])
        self.assertIn(self.user.token, body["feed_url_template"])
        movie = next(entry for entry in body["media_types"] if entry["value"] == "movie")
        self.assertIn("trending_right_now", [row["key"] for row in movie["rows"]])
        with mock.patch("app.discover.feeds.get_feed_row", return_value=None):
            preview = self.client.get(
                body["preview_url"], {"media_type": "movie", "row_key": "trending_right_now"}, **JSON
            )
        self.assertEqual(preview.json(), {"items": []})
        self.assertEqual(self.client.get(body["preview_url"]).status_code, 200)

    def test_rss_is_not_in_the_nav(self):
        nav = self.client.get(reverse("api_settings_screen", args=["account"])).json()["nav"]
        self.assertNotIn("rss", [item["slug"] for section in nav for item in section["items"]])
        self.assertEqual(json.dumps(nav).count('"integrations"'), 1)
