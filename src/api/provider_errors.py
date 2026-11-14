"""FORK: tell a metadata provider's "not found" apart from a provider outage.

API write views resolve the title through TMDB (or another provider) before
they store anything. When the provider is slow, rate limited or down, the
request failed for a temporary reason and the client must retry it, so it
gets 503 with ``Retry-After``. Only the provider itself answering "no such
title" is a 404, which clients may treat as final.
"""

from http import HTTPStatus as HTTP  # noqa: N814

import requests
from rest_framework.response import Response

from app.providers.services import ProviderAPIError
from app.services.episode_coordinates import EpisodeMetadataUnavailableError

PROVIDER_RETRY_AFTER_SECONDS = 30
PROVIDER_UNAVAILABLE_CODE = "provider_unavailable"
PROVIDER_UNAVAILABLE_DETAIL = "Metadata provider unavailable. Try again later."


def is_provider_failure(error):
    """Return True when ``error`` came from a metadata provider call."""
    return isinstance(
        error,
        (
            ProviderAPIError,
            EpisodeMetadataUnavailableError,
            requests.exceptions.RequestException,
        ),
    )


def is_provider_not_found(error):
    """Return True when the provider answered that the title does not exist."""
    status = getattr(error, "status_code", None)
    if status is None and isinstance(error, requests.exceptions.HTTPError):
        status = getattr(error.response, "status_code", None)
    return status == HTTP.NOT_FOUND


def provider_unavailable_response():
    """503 telling the client to retry after the provider recovers."""
    return Response(
        {"detail": PROVIDER_UNAVAILABLE_DETAIL, "code": PROVIDER_UNAVAILABLE_CODE},
        status=HTTP.SERVICE_UNAVAILABLE,
        headers={"Retry-After": str(PROVIDER_RETRY_AFTER_SECONDS)},
    )


def resolution_failure_response(error, not_found_detail):
    """Map an exception raised while resolving a title to an API response.

    404 only for a definite "not found" from the provider, 503 for any other
    provider failure, 500 for everything else (a bug, never a client error).
    """
    if is_provider_failure(error):
        if is_provider_not_found(error):
            return Response({"detail": not_found_detail}, status=HTTP.NOT_FOUND)
        return provider_unavailable_response()
    return Response(
        {"detail": "Internal error while resolving the title.", "code": "server_error"},
        status=HTTP.INTERNAL_SERVER_ERROR,
    )
