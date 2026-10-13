import contextlib
from http import HTTPStatus

from rest_framework.renderers import JSONRenderer

from app.image_cache import rewrite_payload_images

# Machine-readable ``code`` for an error body that names none, by status.
_ERROR_CODES = {
    HTTPStatus.BAD_REQUEST: "bad_request",
    HTTPStatus.UNAUTHORIZED: "not_authenticated",
    HTTPStatus.FORBIDDEN: "permission_denied",
    HTTPStatus.NOT_FOUND: "not_found",
    HTTPStatus.METHOD_NOT_ALLOWED: "method_not_allowed",
    HTTPStatus.CONFLICT: "conflict",
    HTTPStatus.PRECONDITION_FAILED: "precondition_failed",
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "payload_too_large",
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
    HTTPStatus.UNPROCESSABLE_ENTITY: "unprocessable",
    HTTPStatus.TOO_MANY_REQUESTS: "throttled",
    HTTPStatus.BAD_GATEWAY: "provider_unavailable",
    HTTPStatus.SERVICE_UNAVAILABLE: "unavailable",
}


def _with_error_code(data, response):
    """Add ``code`` (and ``retry_after`` on a 429) to a ``{"detail": ...}`` error.

    DRF's own errors carry their code on the detail string (``not_authenticated``,
    ``throttled``, ...); errors views build by hand fall back to the status.
    Bodies that already name a code, and field-error bodies, are left alone.
    """
    if (
        response is None
        or response.status_code < HTTPStatus.BAD_REQUEST
        or not isinstance(data, dict)
        or "detail" not in data
        or "code" in data
    ):
        return data
    code = getattr(data["detail"], "code", None)
    if not code or code in {"invalid", "error"}:
        code = _ERROR_CODES.get(
            response.status_code,
            "server_error"
            if response.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR
            else "error",
        )
    data = {**data, "code": str(code)}
    retry_after = response.get("Retry-After")
    if response.status_code == HTTPStatus.TOO_MANY_REQUESTS and retry_after:
        with contextlib.suppress(ValueError):
            data["retry_after"] = int(retry_after)
    return data


def _set_paging_headers(data, response):
    """Mirror a ``pagination`` envelope into headers clients can read cheaply.

    ``X-Pagination-Item-Count``, ``-Limit`` and ``-Offset``, plus a ``Link``
    header with ``next``/``prev`` (RFC 8288). The body is unchanged.
    """
    if response is None or not isinstance(data, dict):
        return
    pagination = data.get("pagination")
    if not isinstance(pagination, dict):
        return
    for header, key in (
        ("X-Pagination-Item-Count", "total"),
        ("X-Pagination-Limit", "limit"),
        ("X-Pagination-Offset", "offset"),
    ):
        value = pagination.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            response[header] = str(value)
    links = [
        f'<{pagination[key]}>; rel="{rel}"'
        for key, rel in (("next", "next"), ("previous", "prev"))
        if isinstance(pagination.get(key), str) and pagination[key]
    ]
    if links:
        response["Link"] = ", ".join(links)


class ImageCacheJSONRenderer(JSONRenderer):
    """Rewrite approved image fields at the final API representation boundary.

    Also adds a machine-readable ``code`` to error bodies and paging headers to
    paginated responses.
    """

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Rewrite image fields before serializing the API response to JSON."""
        request = (renderer_context or {}).get("request")
        response = (renderer_context or {}).get("response")
        data = _with_error_code(data, response)
        if response is not None and response.status_code < HTTPStatus.BAD_REQUEST:
            _set_paging_headers(data, response)
        return super().render(
            rewrite_payload_images(data, request=request),
            accepted_media_type=accepted_media_type,
            renderer_context=renderer_context,
        )
