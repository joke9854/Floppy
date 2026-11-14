"""FORK: typed JSON errors for exceptions an API view does not handle itself.

DRF handles its own exceptions (validation, auth, throttling, 404). Anything
else used to fall through to ``api.middleware.ApiJsonErrorMiddleware``, which
answers a plain 500 ``{"detail": "Internal server error."}``: a TMDB outage
looked like a server bug, and the body had no ``code``. This handler answers
those inside DRF instead:

- a metadata provider saying "not found": 404 ``not_found``;
- any other provider failure: 503 ``provider_unavailable`` with Retry-After;
- a duplicate tracked-media create: 409, as the middleware did;
- anything else: 500 ``server_error``, logged with its traceback (the error
  tracker picks up the log record). Never exception text.
"""

import logging
from http import HTTPStatus as HTTP  # noqa: N814

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .middleware import _is_media_collection_post, is_tracked_media_unique_error
from .provider_errors import (
    is_provider_failure,
    is_provider_not_found,
    provider_unavailable_response,
)

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    """Return a JSON response for any exception raised by an API view."""
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response

    view = context.get("view")
    view_name = type(view).__name__ if view is not None else "unknown"
    if is_provider_failure(exc):
        if is_provider_not_found(exc):
            return Response(
                {"detail": "Not found at the metadata provider.", "code": "not_found"},
                status=HTTP.NOT_FOUND,
            )
        logger.warning(
            "API provider failure view=%s error=%s status=%s",
            view_name,
            type(exc).__name__,
            getattr(exc, "status_code", None),
        )
        return provider_unavailable_response()

    request = context.get("request")
    path = getattr(request, "path", "") or ""
    if _is_media_collection_post(request, path) and is_tracked_media_unique_error(exc):
        logger.info("Tracked media create conflict: %s", path)
        return Response(
            {"detail": "Conflict. Media is already tracked."},
            status=HTTP.CONFLICT,
        )

    logger.exception("Unhandled API error view=%s", view_name)
    return Response(
        {"detail": "Internal server error.", "code": "server_error"},
        status=HTTP.INTERNAL_SERVER_ERROR,
    )
