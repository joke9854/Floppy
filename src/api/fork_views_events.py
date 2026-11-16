"""FORK (v2 P2-B): live events as server-sent events.

``GET /api/v1/events/`` keeps a connection open and sends the signed-in
user's events as they happen, so a client subscribes once instead of
polling. The stream ends after ``STREAM_SECONDS``; EventSource reconnects by
itself (``retry`` tells it how soon).

Only served over ASGI: under WSGI an open stream would hold a worker thread
for its whole life, so the endpoint answers 503 there.
"""

import json
import time
from http import HTTPStatus as HTTP  # noqa: N814

from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.http import StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import views as drf_views
from rest_framework.response import Response

from app import live_events

from .contract_serializers import DetailErrorSerializer

# Comment line every HEARTBEAT_SECONDS: under nginx's 60 s read timeout and
# the tunnel's idle limit, so an idle stream is never cut.
HEARTBEAT_SECONDS = 20
# Ends each stream so a worker can be recycled and a token revocation takes
# effect; the client reconnects after RETRY_MILLISECONDS.
STREAM_SECONDS = 30 * 60
RETRY_MILLISECONDS = 3000


def _sse(event_type, data):
    return f"event: {event_type}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


async def event_stream(user_id):
    """Yield SSE text for the user's events until STREAM_SECONDS pass."""
    # Authentication and the middleware used the request thread's database
    # connection. The stream needs none and lives for minutes, so give it
    # back now rather than when the response ends. Thread-sensitive, so this
    # runs in the request's own thread, where that connection lives.
    await sync_to_async(connections.close_all)()
    yield f"retry: {RETRY_MILLISECONDS}\n\n"
    deadline = time.monotonic() + STREAM_SECONDS
    stream = live_events.subscribe(user_id, poll_seconds=HEARTBEAT_SECONDS)
    try:
        async for event in stream:
            if event is None:
                yield ": ping\n\n"
            else:
                yield _sse(event.get("type", "message"), event.get("data"))
            if time.monotonic() >= deadline:
                return
    finally:
        await stream.aclose()


class EventsView(drf_views.APIView):
    """Live events for the signed-in user."""

    @extend_schema(
        operation_id="streamEvents",
        summary="Stream live events (server-sent events)",
        description=(
            "A `text/event-stream` of the user's events. Each event has a "
            "`type` (the SSE event name) and JSON `data`. `task.finished` "
            "carries `task_id` and `state` (SUCCESS, FAILURE, ...) when a task "
            "the user started ends; read its result from "
            "`/api/v1/tasks/{task_id}/`. Comment lines (`: ping`) keep the "
            "connection alive. The stream closes after 30 minutes; reconnect "
            "(EventSource does this itself). Events are not stored: one sent "
            "while no stream was open is gone."
        ),
        responses={
            (200, "text/event-stream"): OpenApiTypes.STR,
            503: OpenApiResponse(
                DetailErrorSerializer,
                description="This server runs without live events (WSGI); poll instead.",
            ),
        },
    )
    def get(self, request):
        """Open the stream."""
        if not settings.FLOPPY_ASGI:
            return Response(
                {"detail": "Live events need the ASGI server; poll instead."},
                status=HTTP.SERVICE_UNAVAILABLE,
            )
        response = StreamingHttpResponse(
            event_stream(request.user.id), content_type="text/event-stream"
        )
        response["Cache-Control"] = "no-cache"
        # nginx would otherwise hold events back in its proxy buffer.
        response["X-Accel-Buffering"] = "no"
        return response
