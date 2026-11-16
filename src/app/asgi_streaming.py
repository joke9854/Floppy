"""Stream sync responses chunk by chunk under ASGI (v2 P2-B).

Under ASGI, Django serves a StreamingHttpResponse (and FileResponse) built
on a sync iterator by reading the whole iterator into a list first
(``StreamingHttpResponse.__aiter__``). A library export or a backup download
would sit in memory in full before the first byte went out.

The middleware swaps such a body for an async iterator that pulls one chunk
at a time with ``sync_to_async``. Thread-sensitive calls run in the request's
own thread (Django's handler keeps the request's context until the response
is sent), so iterators that read the database use the request's connection.
Under WSGI the middleware does nothing.
"""

from asgiref.sync import sync_to_async
from django.conf import settings

_DONE = object()


def chunked_async(iterable):
    """Return an async iterator that pulls `iterable` one chunk at a time."""
    iterator = iter(iterable)
    pull = sync_to_async(next)

    async def stream():
        try:
            while True:
                chunk = await pull(iterator, _DONE)
                if chunk is _DONE:
                    return
                yield chunk
        finally:
            close = getattr(iterator, "close", None)
            if close is not None:
                await sync_to_async(close)()

    return stream()


class AsgiStreamingMiddleware:
    """Keep sync streaming bodies streaming when Floppy runs over ASGI."""

    def __init__(self, get_response):
        """Read FLOPPY_ASGI once, as Django builds middleware once."""
        self.get_response = get_response
        self.enabled = settings.FLOPPY_ASGI

    def __call__(self, request):
        """Swap a sync streaming body for a chunked async one."""
        response = self.get_response(request)
        if self.enabled and response.streaming and not response.is_async:
            # FileResponse closes its file through _resource_closers, which
            # the swap keeps; the iterator's own close runs when it ends.
            response.streaming_content = chunked_async(response.streaming_content)
        return response
