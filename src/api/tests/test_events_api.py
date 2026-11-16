"""FORK (v2 P2-B): /api/v1/events/ server-sent events."""

import asyncio
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import AsyncClient, TransactionTestCase, override_settings
from django.urls import reverse

from api import fork_views_events
from app import live_events
from integrations.models import IntegrationToken


def _fake_subscribe(events):
    """Stand-in for live_events.subscribe: the given events, then idle."""

    async def subscribe(user_id, *, poll_seconds):
        for event in events:
            yield event
        while True:
            await asyncio.sleep(0)
            yield None

    return subscribe


class EventsStreamTests(TransactionTestCase):
    """Through the full middleware stack, as the ASGI server serves it."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="live", password="x-12345"
        )
        _, self.raw = IntegrationToken.generate(
            user=self.user, name="live", scopes=["events:read"]
        )
        _, self.narrow = IntegrationToken.generate(
            user=self.user, name="narrow", scopes=["scrobble:write"]
        )

    async def _read_stream(self, token, events):
        client = AsyncClient()
        with (
            patch.object(live_events, "subscribe", _fake_subscribe(events)),
            patch.object(fork_views_events, "STREAM_SECONDS", 0),
        ):
            response = await client.get(
                reverse("api_events"), headers={"X-API-Key": token}
            )
            if not response.streaming:
                return response, b""
            body = b"".join([chunk async for chunk in response.streaming_content])
        return response, body

    @override_settings(FLOPPY_ASGI=True)
    def test_events_stream_as_server_sent_events(self):
        response, body = async_to_sync(self._read_stream)(
            self.raw,
            [{"type": "task.finished", "data": {"task_id": "t-1", "state": "SUCCESS"}}],
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response["Content-Type"], "text/event-stream")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        text = body.decode()
        self.assertTrue(text.startswith("retry: "))
        self.assertIn(
            'event: task.finished\ndata: {"task_id":"t-1","state":"SUCCESS"}\n\n', text
        )

    @override_settings(FLOPPY_ASGI=True)
    def test_a_token_without_events_read_is_refused(self):
        response, _ = async_to_sync(self._read_stream)(self.narrow, [])
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    @override_settings(FLOPPY_ASGI=False)
    def test_wsgi_servers_answer_503(self):
        response, _ = async_to_sync(self._read_stream)(self.raw, [])
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)


class TaskFinishedEventTests(TransactionTestCase):
    def test_only_tasks_with_an_owner_publish(self):
        with patch.object(live_events, "publish") as publish:
            live_events.publish_task_finished("t-1", {"user_id": 7}, "SUCCESS")
            live_events.publish_task_finished("t-2", {}, "SUCCESS")
            live_events.publish_task_finished("t-3", {"user_id": "7"}, "SUCCESS")
        publish.assert_called_once_with(
            7, live_events.TASK_FINISHED, {"task_id": "t-1", "state": "SUCCESS"}
        )

    def test_publish_never_raises(self):
        with patch.object(live_events, "_publisher", side_effect=ConnectionError):
            live_events.publish(1, "x", {})

    def test_eager_tasks_do_not_publish(self):
        from types import SimpleNamespace

        from app.signals import publish_task_finished_event

        with patch.object(live_events, "publish_task_finished") as hook:
            publish_task_finished_event(
                task_id="t",
                task=SimpleNamespace(request=SimpleNamespace(is_eager=True)),
                kwargs={"user_id": 1},
                state="SUCCESS",
            )
        hook.assert_not_called()
