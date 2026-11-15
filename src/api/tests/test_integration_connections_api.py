"""FORK (P1-H): connect, disconnect and run integrations through the API."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from integrations.imports.helpers import encrypt
from integrations.lastfm_api import LastFMAPIError, LastFMClientError
from integrations.models import (
    IntegrationToken,
    JellyfinAccount,
    LastFMAccount,
    RadarrInstance,
)

from .base import FloppyApiTestCase

RECENT_TRACKS = "integrations.connections.lastfm_api.get_recent_tracks"
POLL_TASK = "integrations.tasks.poll_lastfm_for_user.delay"
HISTORY_TASK = "integrations.tasks.import_lastfm_history.delay"


class SessionCase(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user1)
        self.addCleanup(self.client.force_authenticate, user=None)


class StatusTests(FloppyApiTestCase):
    def test_lists_every_service_without_secrets(self):
        JellyfinAccount.objects.create(
            user=self.user1,
            base_url="https://jf.example",
            api_key=encrypt("jf-secret-key"),
            jellyfin_user_id="u1",
            jellyfin_username="me",
        )
        RadarrInstance.objects.create(
            user=self.user1,
            base_url="https://radarr.example",
            api_key=encrypt("radarr-secret"),
        )

        response = self.call_api("get", "api_integrations", headers=self.auth_headers)

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        services = {entry["service"]: entry for entry in body["services"]}
        self.assertTrue(services["jellyfin"]["connected"])
        self.assertEqual(services["jellyfin"]["details"]["jellyfin_username"], "me")
        self.assertFalse(services["lastfm"]["connected"])
        self.assertEqual(body["radarr"][0]["base_url"], "https://radarr.example")
        content = response.content.decode()
        for secret in ("jf-secret-key", "radarr-secret", "api_key", "api_token"):
            self.assertNotIn(secret, content)


class ConnectTests(SessionCase):
    @patch(HISTORY_TASK)
    @patch(POLL_TASK)
    @patch(RECENT_TRACKS, return_value={})
    def test_connect_lastfm_then_poll_and_disconnect(self, _tracks, poll, _history):
        response = self.call_api(
            "put", "api_integration_connection", args=("lastfm",), payload={"username": "me"}
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertTrue(response.json()["connected"])
        self.assertEqual(response.json()["details"]["lastfm_username"], "me")

        poll.return_value.id = "poll-1"
        polled = self.call_api(
            "post", "api_integration_action", args=("lastfm", "poll")
        )
        self.assertEqual(polled.status_code, HTTP.ACCEPTED)
        self.assertEqual(polled.json(), {"task_id": "poll-1", "outcome": "queued"})

        self.assertEqual(
            self.call_api(
                "delete", "api_integration_connection", args=("lastfm",)
            ).status_code,
            HTTP.NO_CONTENT,
        )
        self.assertFalse(LastFMAccount.objects.filter(user=self.user1).exists())

    @patch(RECENT_TRACKS, side_effect=LastFMClientError("User not found"))
    def test_unknown_user_is_400(self, _tracks):
        response = self.call_api(
            "put", "api_integration_connection", args=("lastfm",), payload={"username": "x"}
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)

    @patch(RECENT_TRACKS, side_effect=LastFMAPIError("Connection reset"))
    def test_unreachable_is_503_without_remote_text(self, _tracks):
        response = self.call_api(
            "put", "api_integration_connection", args=("lastfm",), payload={"username": "x"}
        )
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "integration_unreachable")
        self.assertEqual(response["Retry-After"], "30")
        self.assertNotIn("Connection reset", response.content.decode())

    def test_actions_need_a_connection(self):
        response = self.call_api("post", "api_integration_action", args=("lastfm", "poll"))
        self.assertEqual(response.status_code, HTTP.CONFLICT)
        self.assertEqual(response.json()["code"], "not_connected")
        self.assertEqual(
            self.call_api(
                "post", "api_integration_action", args=("lastfm", "explode")
            ).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self.call_api(
                "put", "api_integration_connection", args=("nope",), payload={}
            ).status_code,
            HTTP.NOT_FOUND,
        )

    @patch("integrations.connections.update_jellyfin_settings")
    def test_jellyfin_settings_keep_omitted_flags(self, update):
        JellyfinAccount.objects.create(
            user=self.user1,
            base_url="https://jf.example",
            api_key=encrypt("k"),
            jellyfin_user_id="u1",
            push_watched_enabled=True,
        )
        response = self.call_api(
            "patch",
            "api_integration_settings",
            args=("jellyfin",),
            payload={"pull_history_enabled": True},
        )
        self.assertEqual(response.status_code, HTTP.OK)
        kwargs = update.call_args.kwargs
        self.assertTrue(kwargs["pull_history_enabled"])
        self.assertTrue(kwargs["push_watched_enabled"])
        bad = self.call_api(
            "patch",
            "api_integration_settings",
            args=("jellyfin",),
            payload={"pull_history_enabled": "yes"},
        )
        self.assertEqual(bad.status_code, HTTP.BAD_REQUEST)


class ArrTests(SessionCase):
    @patch("integrations.tasks.import_radarr.delay")
    @patch("integrations.connections.RadarrClient.healthcheck", return_value={})
    def test_add_import_and_remove_a_server(self, _health, import_delay):
        created = self.call_api(
            "post",
            "api_integration_instances",
            args=("radarr",),
            payload={"base_url": "https://radarr.example", "api_key": "k", "name": "4K"},
        )
        self.assertEqual(created.status_code, HTTP.CREATED)
        instance_id = created.json()["id"]
        self.assertNotIn("api_key", created.json())

        import_delay.return_value.id = "imp-1"
        queued = self.call_api(
            "post", "api_integration_instance_import", args=("radarr", instance_id)
        )
        self.assertEqual(queued.json()["task_id"], "imp-1")

        other = RadarrInstance.objects.create(
            user=self.user2, base_url="https://other.example", api_key="x"
        )
        self.assertEqual(
            self.call_api(
                "delete", "api_integration_instance_detail", args=("radarr", other.id)
            ).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self.call_api(
                "delete", "api_integration_instance_detail", args=("radarr", instance_id)
            ).status_code,
            HTTP.NO_CONTENT,
        )
        self.assertTrue(RadarrInstance.objects.filter(id=other.id).exists())


class TokenDenialTests(FloppyApiTestCase):
    def test_no_token_may_connect_disconnect_or_change_settings(self):
        _, raw = IntegrationToken.generate(user=self.user1, name="w", scopes=["*"])
        headers = {"HTTP_X_API_KEY": raw}
        for method, name, args in (
            ("put", "api_integration_connection", ("lastfm",)),
            ("delete", "api_integration_connection", ("lastfm",)),
            ("patch", "api_integration_settings", ("jellyfin",)),
            ("post", "api_integration_instances", ("radarr",)),
            ("delete", "api_integration_instance_detail", ("radarr", 1)),
        ):
            with self.subTest(name=name, method=method):
                response = self.call_api(
                    method, name, args=args, payload={}, headers=headers
                )
                self.assertEqual(response.status_code, HTTP.FORBIDDEN)
