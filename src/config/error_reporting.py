"""Error reporting to a Sentry-compatible server such as GlitchTip.

Off unless ``SENTRY_DSN`` is set. Events never carry credentials: request
headers, cookies, bodies, query strings and local variables are dropped, URLs
lose their query and userinfo, and every message and exception value passes
through the same redaction as the log boundary (see
docs/architecture/log-redaction.md).
"""

import sentry_sdk

from app.log_safety import redact_secrets, safe_url

_REQUEST_KEYS_KEPT = ("method", "url")


def scrub_event(event, _hint=None):
    """Remove anything that could hold a credential from a Sentry event."""
    request = event.get("request")
    if request:
        event["request"] = {
            key: request[key] for key in _REQUEST_KEYS_KEPT if key in request
        }
        if "url" in event["request"]:
            event["request"]["url"] = safe_url(event["request"]["url"])

    if "message" in event:
        event["message"] = redact_secrets(event["message"])
    logentry = event.get("logentry")
    if logentry:
        event["logentry"] = {
            "message": redact_secrets(logentry.get("formatted") or logentry.get("message") or ""),
        }

    for exception in (event.get("exception") or {}).get("values") or []:
        if exception.get("value"):
            exception["value"] = redact_secrets(exception["value"])
        for frame in (exception.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)

    breadcrumbs = event.get("breadcrumbs")
    if breadcrumbs:
        values = breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else breadcrumbs
        for crumb in values:
            scrub_breadcrumb(crumb)

    event.pop("extra", None)
    return event


def scrub_breadcrumb(crumb, _hint=None):
    """Redact a breadcrumb's message and keep only safe data fields."""
    if crumb.get("message"):
        crumb["message"] = redact_secrets(crumb["message"])
    data = crumb.get("data")
    if data:
        safe = {}
        if data.get("url"):
            safe["url"] = safe_url(data["url"])
        for key in ("method", "status_code"):
            if key in data:
                safe[key] = data[key]
        crumb["data"] = safe
    return crumb


def init_error_reporting(dsn, *, release, environment):
    """Start the Sentry SDK with Floppy's privacy settings."""
    sentry_sdk.init(
        dsn=dsn,
        release=release,
        environment=environment,
        send_default_pii=False,
        include_local_variables=False,
        include_source_context=False,
        max_request_body_size="never",
        traces_sample_rate=0,
        before_send=scrub_event,
        before_breadcrumb=scrub_breadcrumb,
    )
