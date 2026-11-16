"""gunicorn worker that serves ``config.asgi`` with uvicorn (v2 P2-B).

gunicorn keeps managing processes (preload, fork, max_requests, timeout,
graceful restarts). Two things gthread did through gunicorn hooks are done
here instead, because the uvicorn worker never calls ``post_request``:

- **Memory ceiling:** the worker checks its resident size on each heartbeat
  and retires itself above ``max_worker_memory_bytes``, with the same floors
  as before (``config.gunicorn.worker_should_retire``).
- **Bounded shutdown:** an open event stream never ends by itself, so a
  retiring worker waits at most gunicorn's ``graceful_timeout`` for requests
  in flight, then closes them.
"""

import warnings

with warnings.catch_warnings():
    # uvicorn.workers is deprecated in favour of the uvicorn-worker package;
    # it is what the locked uvicorn ships, and this subclass is the only user.
    warnings.simplefilter("ignore", DeprecationWarning)
    from uvicorn.workers import UvicornWorker

from uvicorn.server import Server


class FloppyUvicornWorker(UvicornWorker):
    """UvicornWorker with Floppy's memory ceiling and a bounded shutdown."""

    # Django has no ASGI lifespan support; "off" skips uvicorn's probe and its
    # misleading "lifespan unsupported" line on every start.
    CONFIG_KWARGS = {"loop": "auto", "http": "auto", "lifespan": "off"}

    def __init__(self, *args, **kwargs):
        """Bound shutdown by gunicorn's graceful_timeout."""
        super().__init__(*args, **kwargs)
        self.config.timeout_graceful_shutdown = self.cfg.graceful_timeout
        self._floppy_server = None

    async def _serve(self):
        # Same as UvicornWorker._serve, keeping the server so the heartbeat
        # can ask it to exit.
        import sys

        from gunicorn.arbiter import Arbiter

        self.config.app = self.wsgi
        server = Server(config=self.config)
        self._floppy_server = server
        self._install_sigquit_handler()
        await server.serve(sockets=self.sockets)
        if not server.started:
            sys.exit(Arbiter.WORKER_BOOT_ERROR)

    async def callback_notify(self):
        """Heartbeat to the arbiter, then retire the worker if it is too big."""
        self.notify()
        server = self._floppy_server
        if server is None or server.should_exit:
            return
        from config.gunicorn import worker_should_retire

        if worker_should_retire(
            server.server_state.total_requests,
            getattr(self, "floppy_started_at", None),
        ):
            self.log.info("[gunicorn] worker over its memory ceiling; retiring")
            server.should_exit = True
