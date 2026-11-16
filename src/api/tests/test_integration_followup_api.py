"""FORK (P1-H follow-up): webhook filters, Plex shares, Plex and scheduled imports."""

import io
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.urls import reverse
from django_celery_beat.models import PeriodicTask

from integrations.imports.helpers import encrypt
from integrations.models import (
    IntegrationToken,
    JellyfinAccount,
    KoreaderAccount,
    PlexAccount,
    PlexWebhookShare,
)
from integrations.upload_staging import discard_staged_upload

from .base import FloppyApiTestCase

SECTIONS = [
    {"machine_identifier": "m1", "id": "1", "title": "Movies", "server_name": "Home"},
    {"machine_identifier": "m1", "id": "2", "title": "Music", "server_name": "Home"},
]


def _plex(user):
    return PlexAccount.objects.create(
        user=user, plex_token="t", plex_username="owner", sections=SECTIONS
    )


class WebhookSettingsTests(FloppyApiTestCase):
    def _patch(self, payload):
        return self.call_api(
            "patch",
            "api_user_webhook_settings",
            payload=payload,
            headers=self.auth_headers,
        )

    def test_read_and_change_every_filter(self):
        _plex(self.user1)

        response = self._patch(
            {
                "plex_usernames": [" me ", "Kid", "me"],
                "plex_webhook_libraries": ["m1::1", "m9::9"],
                "plex_content_kinds": {"m1::2": "audiobook"},
                "jellyfin_mark_played_enabled": True,
                "seerr": {"enabled": True, "trigger_statuses": ["pending"]},
            }
        )

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["plex_usernames"], ["me", "Kid"])
        self.assertEqual(body["plex_webhook_libraries"], ["m1::1"])
        kinds = {lib["value"]: lib["content_kind"] for lib in body["plex_libraries"]}
        self.assertEqual(kinds["m1::2"], "audiobook")
        self.assertTrue(body["jellyfin_mark_played_enabled"])
        self.assertEqual(body["seerr"]["trigger_statuses"], ["PENDING"])
        self.assertTrue(body["seerr"]["enabled"])

    def test_bad_values_are_400(self):
        _plex(self.user1)
        for payload in (
            {"plex_usernames": "me"},
            {"jellyfin_mark_played_enabled": "yes"},
            {"plex_content_kinds": {"m1::1": "podcast"}},
            {"plex_content_kinds": {"m9::9": "music"}},
            {"seerr": {"trigger_statuses": ["SOON"]}},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self._patch(payload).status_code, HTTP.BAD_REQUEST)


class PlexShareTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        _plex(self.user1)

    def _as(self, user):
        self.client.force_authenticate(user=user)
        self.addCleanup(self.client.force_authenticate, user=None)

    def test_owner_shares_and_recipient_enables(self):
        self._as(self.user1)
        created = self.call_api(
            "post",
            "api_plex_shares",
            payload={
                "recipient_id": self.user2.id,
                "plex_usernames": ["Kid"],
                "allowed_libraries": ["m1::1"],
            },
        )
        self.assertEqual(created.status_code, HTTP.CREATED)
        share_id = created.json()["id"]
        listed = self.call_api("get", "api_plex_shares").json()
        self.assertEqual([s["id"] for s in listed["owned"]], [share_id])
        self.assertIn(self.user2.id, [r["id"] for r in listed["recipients"]])

        self._as(self.user2)
        enabled = self.call_api(
            "put", "api_plex_share_enabled", args=(share_id,), payload={"enabled": True}
        )
        self.assertEqual(enabled.status_code, HTTP.OK)
        self.assertTrue(PlexWebhookShare.objects.get(id=share_id).recipient_enabled)
        # The recipient cannot edit or revoke the owner's share.
        self.assertEqual(
            self.call_api("delete", "api_plex_share_detail", args=(share_id,)).status_code,
            HTTP.NOT_FOUND,
        )

        self._as(self.user1)
        self.assertEqual(
            self.call_api(
                "post",
                "api_plex_shares",
                payload={"recipient_id": self.user1.id, "plex_usernames": ["x"]},
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.call_api("delete", "api_plex_share_detail", args=(share_id,)).status_code,
            HTTP.NO_CONTENT,
        )

    def test_tokens_cannot_share(self):
        _, raw = IntegrationToken.generate(user=self.user1, name="w", scopes=["*"])
        response = self.call_api(
            "post",
            "api_plex_shares",
            payload={"recipient_id": self.user2.id, "plex_usernames": ["Kid"]},
            headers={"HTTP_X_API_KEY": raw},
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)


class ImportFollowupTests(FloppyApiTestCase):
    @patch("integrations.tasks.import_plex.delay")
    def test_plex_import_now_and_scheduled(self, delay):
        _plex(self.user1)
        delay.return_value.id = "plex-1"
        now = self.call_api(
            "post",
            "api_integration_import",
            args=("plex",),
            payload={"libraries": ["m1::1"]},
            headers=self.auth_headers,
        )
        self.assertEqual(now.status_code, HTTP.ACCEPTED)
        self.assertEqual(now.json(), {"task_id": "plex-1", "outcome": "queued"})
        delay.assert_called_once_with(library=["m1::1"], user_id=self.user1.id, mode="new")

        scheduled = self.call_api(
            "post",
            "api_integration_import",
            args=("plex",),
            payload={"frequency": "daily", "time": "05:30"},
            headers=self.auth_headers,
        )
        self.assertEqual(scheduled.json()["outcome"], "scheduled")
        self.assertTrue(
            PeriodicTask.objects.filter(task="Import from Plex", name__contains="05:30").exists()
        )
        bad = self.call_api(
            "post",
            "api_integration_import",
            args=("plex",),
            payload={"libraries": ["m9::9"]},
            headers=self.auth_headers,
        )
        self.assertEqual(bad.status_code, HTTP.BAD_REQUEST)

    def test_koreader_schedule(self):
        KoreaderAccount.objects.create(
            user=self.user1, server_url="https://ko.example", username="reader", auth_key="x"
        )
        response = self.call_api(
            "post",
            "api_integration_import",
            args=("koreader",),
            payload={"frequency": "2days", "time": "01:00"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        self.assertEqual(response.json()["outcome"], "scheduled")
        self.assertTrue(
            PeriodicTask.objects.filter(task="Import from KOReader").exists()
        )

    def test_username_import_on_a_schedule(self):
        response = self.call_api(
            "post",
            "api_import_dispatch",
            args=("mal",),
            payload={"username": "someone", "frequency": "daily", "time": "02:00"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.CREATED)
        task = PeriodicTask.objects.get(id=response.json()["schedule_id"])
        self.assertEqual(task.task, "Import from MyAnimeList")
        again = self.call_api(
            "post",
            "api_import_dispatch",
            args=("mal",),
            payload={"username": "someone", "frequency": "daily", "time": "02:00"},
            headers=self.auth_headers,
        )
        self.assertEqual(again.status_code, HTTP.BAD_REQUEST)

    @patch("integrations.tasks.import_jellyfin_playback_reporting.delay")
    def test_playback_reporting_upload(self, delay):
        delay.return_value.id = "pr-1"
        url = reverse("api_jellyfin_playback_reporting")
        upload = io.BytesIO(b"DateCreated\tUserId\n")
        upload.name = "playback.tsv"
        not_connected = self.client.post(url, {"file": upload}, **self.auth_headers)
        self.assertEqual(not_connected.status_code, HTTP.CONFLICT)

        JellyfinAccount.objects.create(
            user=self.user1,
            base_url="https://jf.example",
            api_key=encrypt("k"),
            jellyfin_user_id="u1",
        )
        upload.seek(0)
        response = self.client.post(url, {"file": upload}, **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        staged = delay.call_args.args[0]
        self.addCleanup(discard_staged_upload, staged)
        self.assertEqual(delay.call_args.args[1:], (self.user1.id, "new"))
