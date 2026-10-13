# FORK: tests for Authenticated Client Identity and Durable Idempotency (PR2).
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import MagicMock, patch

from rest_framework.response import Response

from app.models import PlaybackProgress
from integrations.delivery import calculate_payload_digest, get_or_record_receipt
from integrations.models import IntegrationEventReceipt, IntegrationToken

from .base import FloppyApiTestCase


class DeliveryPayloadDigestTests(FloppyApiTestCase):
    """Unit tests for deterministic payload digest calculation."""

    def test_digest_deterministic_key_order(self):
        """Dicts with different key insertion order must produce identical SHA-256 digests."""
        payload1 = {"action": "stop", "media_type": "movie", "position_seconds": 120}
        payload2 = {"position_seconds": 120, "action": "stop", "media_type": "movie"}
        self.assertEqual(
            calculate_payload_digest(payload1),
            calculate_payload_digest(payload2),
        )

    def test_digest_nested_structures(self):
        """Nested dictionaries and lists are canonicalized deterministically."""
        payload1 = {
            "ids": {"tmdb": "603", "imdb": "tt0133093"},
            "tags": ["sci-fi", "action"],
        }
        payload2 = {
            "ids": {"imdb": "tt0133093", "tmdb": "603"},
            "tags": ["sci-fi", "action"],
        }
        self.assertEqual(
            calculate_payload_digest(payload1),
            calculate_payload_digest(payload2),
        )

    def test_digest_json_string_and_bytes(self):
        """JSON strings and byte sequences are parsed and digested canonically."""
        payload_dict = {"a": 1, "b": 2}
        payload_str = '{"b": 2, "a": 1}'
        payload_bytes = b'{"b": 2, "a": 1}'
        expected = calculate_payload_digest(payload_dict)

        self.assertEqual(calculate_payload_digest(payload_str), expected)
        self.assertEqual(calculate_payload_digest(payload_bytes), expected)


class DeliveryReceiptGatewayTests(FloppyApiTestCase):
    """Unit tests for get_or_record_receipt gateway behavior."""

    def test_new_receipt_executes_and_persists(self):
        """Unseen client_event_id executes the callback and creates a database receipt."""
        mock_fn = MagicMock(return_value=Response({"status": "ok"}, status=HTTP.OK))
        payload = {"action": "stop"}

        response, is_replay = get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-001",
            payload=payload,
            execute_fn=mock_fn,
        )

        self.assertFalse(is_replay)
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.data, {"status": "ok"})
        mock_fn.assert_called_once()

        receipt = IntegrationEventReceipt.objects.get(user=self.user1, client_event_id="evt-001")
        self.assertEqual(receipt.response_status_code, 200)
        self.assertEqual(receipt.response_body, {"status": "ok"})
        self.assertEqual(receipt.payload_digest, calculate_payload_digest(payload))
        self.assertIsNone(receipt.token)
        self.assertEqual(str(receipt), f"IntegrationEventReceipt({self.user1.username}, evt-001)")

    def test_replay_returns_cached_response_without_reexecution(self):
        """Identical payload on existing client_event_id returns cached response without callback."""
        mock_fn = MagicMock(return_value=Response({"detail": "processed"}, status=HTTP.OK))
        payload = {"action": "stop", "media_type": "movie"}

        # First call
        res1, is_replay1 = get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-002",
            payload=payload,
            execute_fn=mock_fn,
        )
        self.assertFalse(is_replay1)
        self.assertEqual(mock_fn.call_count, 1)

        # Replay call with same payload
        res2, is_replay2 = get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-002",
            payload=payload,
            execute_fn=mock_fn,
        )
        self.assertTrue(is_replay2)
        self.assertEqual(res2.status_code, HTTP.OK)
        self.assertEqual(res2.data, {"detail": "processed"})
        self.assertEqual(mock_fn.call_count, 1)  # NOT called again

    def test_conflict_returns_409_on_payload_mismatch(self):
        """Different payload on existing client_event_id returns 409 Conflict."""
        mock_fn = MagicMock(return_value=Response({"detail": "done"}, status=HTTP.OK))

        get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-003",
            payload={"action": "start"},
            execute_fn=mock_fn,
        )

        res_conflict, is_replay = get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-003",
            payload={"action": "stop"},
            execute_fn=mock_fn,
        )
        self.assertFalse(is_replay)
        self.assertEqual(res_conflict.status_code, HTTP.CONFLICT)
        self.assertEqual(
            res_conflict.data,
            {
                "error": {
                    "type": "conflict_error",
                    "code": "idempotency_conflict",
                    "message": (
                        "The provided Idempotency-Key has already been used "
                        "with a different request payload."
                    ),
                    "param": "Idempotency-Key",
                    "correlation_id": "rec_evt-003",
                }
            },
        )
        self.assertEqual(mock_fn.call_count, 1)

    def test_user_isolation_for_same_client_event_id(self):
        """Two different users can use the same client_event_id independently."""
        fn1 = MagicMock(return_value=Response({"user": 1}, status=HTTP.OK))
        fn2 = MagicMock(return_value=Response({"user": 2}, status=HTTP.OK))

        res1, _ = get_or_record_receipt(
            user=self.user1,
            client_event_id="shared-evt-id",
            payload={"val": "u1"},
            execute_fn=fn1,
        )
        res2, _ = get_or_record_receipt(
            user=self.user2,
            client_event_id="shared-evt-id",
            payload={"val": "u2"},
            execute_fn=fn2,
        )

        self.assertEqual(res1.data, {"user": 1})
        self.assertEqual(res2.data, {"user": 2})
        self.assertTrue(
            IntegrationEventReceipt.objects.filter(user=self.user1, client_event_id="shared-evt-id").exists()
        )
        self.assertTrue(
            IntegrationEventReceipt.objects.filter(user=self.user2, client_event_id="shared-evt-id").exists()
        )

    def test_token_association_persisted(self):
        """When an IntegrationToken is provided, receipt links to it."""
        token, _ = IntegrationToken.generate(user=self.user1, name="My TV")
        mock_fn = MagicMock(return_value=Response({"saved": True}, status=HTTP.OK))

        get_or_record_receipt(
            user=self.user1,
            client_event_id="evt-with-token",
            payload={"action": "start"},
            execute_fn=mock_fn,
            token=token,
        )

        receipt = IntegrationEventReceipt.objects.get(user=self.user1, client_event_id="evt-with-token")
        self.assertEqual(receipt.token, token)


class ScrobbleIdempotencyTests(FloppyApiTestCase):
    """End-to-end idempotency and receipt tests on /api/v1/scrobble/."""

    def setUp(self):
        super().setUp()
        self.token, self.raw_token = IntegrationToken.generate(
            user=self.user1,
            name="Living Room Stremio",
        )
        self.integration_headers = {"HTTP_X_API_KEY": self.raw_token}

    def test_scrobble_with_idempotency_key_header(self):
        """Scrobble endpoint records receipt and skips processing on replay."""
        movie_item = self.items_by_type["movie"][0]
        payload = {
            "action": "start",
            "media_type": "movie",
            "ids": {"tmdb": movie_item.media_id},
        }
        headers = {**self.integration_headers, "HTTP_IDEMPOTENCY_KEY": "scrobble-key-1"}

        # 1. Initial request
        res1 = self.call_api("post", "api_scrobble", payload=payload, headers=headers)
        self.assertEqual(res1.status_code, HTTP.OK)
        self.assertEqual(res1.data["detail"], "accepted")
        self.assertEqual(res1.data["action"], "start")

        receipt = IntegrationEventReceipt.objects.get(user=self.user1, client_event_id="scrobble-key-1")
        self.assertEqual(receipt.response_status_code, HTTP.OK)
        self.assertEqual(receipt.token, self.token)

        # 2. Replay with identical payload returns cached 200 without reprocessing
        with patch("api.fork_views_scrobble.ScrobbleView._update_live_playback") as mock_live:
            res2 = self.call_api("post", "api_scrobble", payload=payload, headers=headers)
            self.assertEqual(res2.status_code, HTTP.OK)
            self.assertEqual(res2.data, res1.data)
            mock_live.assert_not_called()

        # 3. Request with same key but different payload returns 409 Conflict
        res3 = self.call_api(
            "post",
            "api_scrobble",
            payload={"action": "stop", "media_type": "movie", "ids": {"tmdb": movie_item.media_id}},
            headers=headers,
        )
        self.assertEqual(res3.status_code, HTTP.CONFLICT)
        self.assertEqual(res3.data["error"]["code"], "idempotency_conflict")

    def test_scrobble_with_client_event_id_in_body(self):
        """Scrobble endpoint honors client_event_id supplied in JSON payload."""
        movie_item = self.items_by_type["movie"][0]
        payload = {
            "client_event_id": "body-event-99",
            "action": "start",
            "media_type": "movie",
            "ids": {"tmdb": movie_item.media_id},
        }

        res1 = self.call_api("post", "api_scrobble", payload=payload, headers=self.integration_headers)
        self.assertEqual(res1.status_code, HTTP.OK)

        self.assertTrue(
            IntegrationEventReceipt.objects.filter(user=self.user1, client_event_id="body-event-99").exists()
        )

        # Replay identical payload
        res2 = self.call_api("post", "api_scrobble", payload=payload, headers=self.integration_headers)
        self.assertEqual(res2.status_code, HTTP.OK)

        # Conflict on same client_event_id with different payload
        conflict_payload = {**payload, "action": "stop"}
        res3 = self.call_api("post", "api_scrobble", payload=conflict_payload, headers=self.integration_headers)
        self.assertEqual(res3.status_code, HTTP.CONFLICT)


class PlaybackProgressIdempotencyTests(FloppyApiTestCase):
    """End-to-end idempotency tests on /api/v1/playback/progress/."""

    def setUp(self):
        super().setUp()
        self.token, self.raw_token = IntegrationToken.generate(
            user=self.user1,
            name="Tablet Player",
        )
        self.integration_headers = {"HTTP_X_API_KEY": self.raw_token}

    def test_playback_progress_put_idempotency(self):
        """Playback progress PUT creates receipt and replays cached response."""
        movie_item = self.items_by_type["movie"][0]
        payload = {
            "media_type": "movie",
            "ids": {"tmdb": movie_item.media_id},
            "position_seconds": 350,
            "duration_seconds": 7200,
        }
        headers = {**self.integration_headers, "HTTP_IDEMPOTENCY_KEY": "progress-put-1"}

        res1 = self.call_api("put", "api_playback_progress", payload=payload, headers=headers)
        self.assertEqual(res1.status_code, HTTP.OK)
        self.assertEqual(res1.data["position_seconds"], 350)

        # Verify DB progress record was created
        p = PlaybackProgress.objects.get(user=self.user1, item=movie_item)
        self.assertEqual(p.position_seconds, 350)

        # Replay identical PUT
        with patch("api.fork_views_playback.upsert_playback_progress") as mock_upsert:
            res2 = self.call_api("put", "api_playback_progress", payload=payload, headers=headers)
            self.assertEqual(res2.status_code, HTTP.OK)
            self.assertEqual(res2.data["position_seconds"], 350)
            mock_upsert.assert_not_called()

        # Same key with different payload returns 409 Conflict
        res3 = self.call_api(
            "put",
            "api_playback_progress",
            payload={**payload, "position_seconds": 600},
            headers=headers,
        )
        self.assertEqual(res3.status_code, HTTP.CONFLICT)
        self.assertEqual(res3.data["error"]["code"], "idempotency_conflict")

    def test_playback_progress_user_isolation(self):
        """User 1 and User 2 using identical Idempotency-Key have isolated receipts."""
        movie_item = self.items_by_type["movie"][0]
        key = "shared-idempotency-key"

        res1 = self.call_api(
            "put",
            "api_playback_progress",
            payload={"media_type": "movie", "ids": {"tmdb": movie_item.media_id}, "position_seconds": 100},
            headers={**self.auth_headers, "HTTP_IDEMPOTENCY_KEY": key},
        )
        self.assertEqual(res1.status_code, HTTP.OK)

        res2 = self.call_api(
            "put",
            "api_playback_progress",
            payload={"media_type": "movie", "ids": {"tmdb": movie_item.media_id}, "position_seconds": 200},
            headers={**self.auth_headers2, "HTTP_IDEMPOTENCY_KEY": key},
        )
        self.assertEqual(res2.status_code, HTTP.OK)

        p1 = PlaybackProgress.objects.get(user=self.user1, item=movie_item)
        p2 = PlaybackProgress.objects.get(user=self.user2, item=movie_item)
        self.assertEqual(p1.position_seconds, 100)
        self.assertEqual(p2.position_seconds, 200)

    def test_playback_progress_delete_idempotency(self):
        """Playback progress DELETE supports Idempotency-Key and replays cleanly."""
        movie_item = self.items_by_type["movie"][0]
        PlaybackProgress.objects.create(user=self.user1, item=movie_item, position_seconds=300)

        payload = {"media_type": "movie", "ids": {"tmdb": movie_item.media_id}}
        headers = {**self.auth_headers, "HTTP_IDEMPOTENCY_KEY": "del-key-1"}

        res1 = self.call_api("delete", "api_playback_progress", payload=payload, headers=headers)
        self.assertEqual(res1.status_code, HTTP.NO_CONTENT)
        self.assertFalse(PlaybackProgress.objects.filter(user=self.user1, item=movie_item).exists())

        # Replay delete
        res2 = self.call_api("delete", "api_playback_progress", payload=payload, headers=headers)
        self.assertEqual(res2.status_code, HTTP.NO_CONTENT)
