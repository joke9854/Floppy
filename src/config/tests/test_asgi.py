"""v2 P2-B: the web process over ASGI."""

import asyncio
import sys
from unittest import mock, skipIf

from django.http import StreamingHttpResponse
from django.test import SimpleTestCase, override_settings

from app.asgi_streaming import AsgiStreamingMiddleware, chunked_async
from config.asgi import ConcurrencyLimit


class ConcurrencyLimitTests(SimpleTestCase):
    def _run(self, limit, paths):
        state = {"inside": 0, "peak": 0}

        async def app(scope, receive, send):
            state["inside"] += 1
            state["peak"] = max(state["peak"], state["inside"])
            await asyncio.sleep(0.01)
            state["inside"] -= 1

        limited = ConcurrencyLimit(app, limit)

        async def main():
            await asyncio.gather(
                *(limited({"type": "http", "path": p}, None, None) for p in paths)
            )

        asyncio.run(main())
        return state["peak"]

    def test_requests_wait_for_a_slot(self):
        self.assertEqual(self._run(2, ["/api/v1/media/movie/"] * 8), 2)

    def test_event_streams_do_not_take_a_slot(self):
        self.assertEqual(self._run(1, ["/api/v1/events/"] * 4), 4)


class StreamingTests(SimpleTestCase):
    def test_chunked_async_yields_every_chunk_and_closes(self):
        closed = []

        def rows():
            try:
                yield b"a"
                yield b"b"
            finally:
                closed.append(True)

        async def collect():
            return [chunk async for chunk in chunked_async(rows())]

        self.assertEqual(asyncio.run(collect()), [b"a", b"b"])
        self.assertEqual(closed, [True])

    def _response_through(self, enabled):
        with override_settings(FLOPPY_ASGI=enabled):
            middleware = AsgiStreamingMiddleware(
                lambda _request: StreamingHttpResponse(iter([b"x", b"y"]))
            )
        return middleware(None)

    def test_asgi_turns_sync_streams_async(self):
        response = self._response_through(enabled=True)
        self.assertTrue(response.is_async)

        async def body():
            return b"".join([part async for part in response])

        self.assertEqual(asyncio.run(body()), b"xy")

    def test_wsgi_leaves_streams_alone(self):
        self.assertFalse(self._response_through(enabled=False).is_async)


@skipIf(sys.platform == "win32", "config.gunicorn reads os.sysconf")
class WorkerRetirementTests(SimpleTestCase):
    """The ASGI worker's heartbeat uses the same rule as the gthread hook."""

    def test_rule_matches_the_hook_floors(self):
        from config import gunicorn as gunicorn_config

        with (
            mock.patch.object(gunicorn_config, "max_worker_memory_bytes", 100),
            mock.patch.object(gunicorn_config, "_worker_rss_bytes", return_value=200),
        ):
            minimum = gunicorn_config.MINIMUM_REQUESTS_BEFORE_RETIREMENT
            self.assertFalse(gunicorn_config.worker_should_retire(minimum - 1, None))
            self.assertTrue(gunicorn_config.worker_should_retire(minimum, None))

    def test_floppy_asgi_selects_a_loadable_uvicorn_worker(self):
        import importlib

        from gunicorn.util import load_class

        from config import gunicorn as gunicorn_config

        try:
            with mock.patch.dict("os.environ", {"FLOPPY_ASGI": "true"}):
                importlib.reload(gunicorn_config)
            worker = load_class(gunicorn_config.worker_class)
            self.assertEqual(worker.__name__, "FloppyUvicornWorker")
            self.assertEqual(worker.CONFIG_KWARGS["lifespan"], "off")
        finally:
            with mock.patch.dict("os.environ", {"FLOPPY_ASGI": ""}):
                importlib.reload(gunicorn_config)
        self.assertEqual(gunicorn_config.worker_class, "gthread")
