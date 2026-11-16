"""ASGI entry point for the Floppy web process (v2 P2-B).

gunicorn runs this with ``config.asgi_worker.FloppyUvicornWorker``.
``config/wsgi.py`` stays for ``runserver``, source installs and the bench
script.

Django runs each sync view in a thread of its own under ASGI, so nothing
caps how many run at once the way gthread's ``GUNICORN_THREADS`` did. The
cap is kept here: at most that many requests per worker are inside Django
at a time and the rest wait, as they waited for a free thread before. The
Postgres pool is sized from the same number (``DB_POOL_MAX``), so it can't
run out.
"""

import asyncio
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

django_application = get_asgi_application()

# Long-lived streams hold their slot for hours; they release the database
# before streaming and must not block ordinary requests.
UNCAPPED_PATH_PREFIXES = ("/api/v1/events",)


class ConcurrencyLimit:
    """Let at most `limit` HTTP requests into the wrapped app at once."""

    def __init__(self, app, limit, uncapped_prefixes=UNCAPPED_PATH_PREFIXES):
        """Wrap `app`; the semaphore is made later, in the worker's loop."""
        self.app = app
        self.limit = max(1, int(limit))
        self.uncapped_prefixes = uncapped_prefixes
        self._semaphore = None

    async def __call__(self, scope, receive, send):
        """Pass the request on once a slot is free."""
        if scope["type"] != "http" or scope.get("path", "").startswith(
            self.uncapped_prefixes
        ):
            await self.app(scope, receive, send)
            return
        # Created on first use, inside the worker's event loop.
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.limit)
        async with self._semaphore:
            await self.app(scope, receive, send)


def _request_limit():
    from config.runtime_profile import gunicorn_threads

    return gunicorn_threads()


application = ConcurrencyLimit(django_application, _request_limit())
