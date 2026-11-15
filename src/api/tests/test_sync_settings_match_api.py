"""FORK (P1-H): sync direction and pause; match review."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from integrations.imports.helpers import encrypt
from integrations.models import (
    ExternalReference,
    ExternalReferenceReviewStatus,
    IntegrationToken,
    JellyfinAccount,
    SyncBindingStatus,
    SyncClientKind,
)
from integrations.state.identity import get_or_create_binding

from .base import FloppyApiTestCase


class SyncSettingsTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        JellyfinAccount.objects.create(
            user=self.user1,
            base_url="https://jf.example",
            api_key=encrypt("secret"),
            jellyfin_user_id="jf-user",
        )
        self.binding, _ = get_or_create_binding(
            self.user1,
            SyncClientKind.JELLYFIN.value,
            instance_key="s",
            profile_key="jf-user",
        )
        self.client.force_authenticate(user=self.user1)
        self.addCleanup(self.client.force_authenticate, user=None)

    def _patch(self, payload, binding_id=None):
        return self.call_api(
            "patch",
            "api_sync_setting_detail",
            args=(binding_id or self.binding.pk,),
            payload=payload,
        )

    def test_list_then_turn_on_both_and_pause(self):
        listed = self.call_api("get", "api_sync_settings").json()["results"]
        self.assertEqual([row["id"] for row in listed], [self.binding.pk])
        self.assertEqual(listed[0]["direction"], "off")

        response = self._patch({"direction": "both", "kill_switch": True})

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["direction"], "both")
        self.assertTrue(body["kill_switch"])
        self.binding.refresh_from_db()
        self.assertEqual(self.binding.status, SyncBindingStatus.ACTIVE.value)
        self.assertTrue(self.binding.kill_switch)

        self._patch({"direction": "off"})
        self.binding.refresh_from_db()
        self.assertEqual(self.binding.status, SyncBindingStatus.DISABLED.value)

    def test_bad_input_and_other_users_binding(self):
        self.assertEqual(
            self._patch({"direction": "sideways"}).status_code, HTTP.BAD_REQUEST
        )
        self.assertEqual(
            self._patch({"kill_switch": "yes"}).status_code, HTTP.BAD_REQUEST
        )
        other, _ = get_or_create_binding(
            self.user2,
            SyncClientKind.JELLYFIN.value,
            instance_key="s",
            profile_key="other",
        )
        self.assertEqual(
            self._patch({"kill_switch": True}, binding_id=other.pk).status_code,
            HTTP.NOT_FOUND,
        )

    def test_tokens_cannot_change_sync_consent(self):
        self.client.force_authenticate(user=None)
        _, raw = IntegrationToken.generate(user=self.user1, name="w", scopes=["*"])
        response = self.call_api(
            "patch",
            "api_sync_setting_detail",
            args=(self.binding.pk,),
            payload={"direction": "both"},
            headers={"HTTP_X_API_KEY": raw},
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)


class MatchReviewTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.movie = self.movie_medias[0]
        self.reference = ExternalReference.objects.create(
            user=self.user1,
            integration="plex",
            external_namespace="plex",
            external_identity="guid-1",
            media_type="movie",
            matched_item=self.movie.item,
            review_status=ExternalReferenceReviewStatus.NEEDS_REVIEW.value,
        )

    def test_list_and_decide(self):
        listed = self.call_api(
            "get", "api_match_references", headers=self.auth_headers
        ).json()
        self.assertEqual([r["id"] for r in listed["needs_review"]], [self.reference.id])
        self.assertEqual(
            listed["needs_review"][0]["matched_item"]["id"], self.movie.item.id
        )

        ignored = self.call_api(
            "post",
            "api_match_reference_decision",
            args=(self.reference.id,),
            payload={"decision": "ignore"},
            headers=self.auth_headers,
        )
        self.assertEqual(ignored.json()["review_status"], "ignored")
        other = self.call_api(
            "post",
            "api_match_reference_decision",
            args=(self.reference.id,),
            payload={"decision": "ignore"},
            headers=self.auth_headers2,
        )
        self.assertEqual(other.status_code, HTTP.NOT_FOUND)

    @patch(
        "app.providers.services.get_media_metadata",
        return_value={"title": "Right Movie", "image": ""},
    )
    def test_preview_then_apply_and_stale_token(self, _metadata):
        preview = self.call_api(
            "post",
            "api_match_fix_preview",
            args=(self.movie.item.id,),
            payload={"destination_media_id": "999001"},
            headers=self.auth_headers,
        )
        self.assertEqual(preview.status_code, HTTP.OK)
        body = preview.json()

        stale = self.call_api(
            "post",
            "api_match_fix_apply",
            args=(self.movie.item.id,),
            payload={"destination_item_id": body["destination_item_id"], "token": "x"},
            headers=self.auth_headers,
        )
        self.assertEqual(stale.status_code, HTTP.CONFLICT)

        applied = self.call_api(
            "post",
            "api_match_fix_apply",
            args=(self.movie.item.id,),
            payload={
                "destination_item_id": body["destination_item_id"],
                "token": body["token"],
            },
            headers=self.auth_headers,
        )
        self.assertEqual(applied.status_code, HTTP.OK)
        self.assertEqual(applied.json()["media_id"], "999001")
        self.reference.refresh_from_db()
        self.assertEqual(self.reference.corrected_item_id, body["destination_item_id"])

    def test_untracked_source_is_404(self):
        response = self.call_api(
            "post",
            "api_match_fix_preview",
            args=(self.movie.item.id,),
            payload={"destination_media_id": "1"},
            headers=self.auth_headers2,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
