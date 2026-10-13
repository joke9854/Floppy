"""Request limits for ``/api/v1/``: a 429 with ``Retry-After`` past the budget.

One budget per account, shared by every app and key it uses, and a smaller one
per address for requests without credentials. The rates come from settings
(``API_RATE_LIMIT`` and ``API_ANON_RATE_LIMIT``) and are read on every
request, so a self-hoster can raise or disable them without code changes.
"""

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class _SettingsRateThrottle(SimpleRateThrottle):
    """A throttle whose rate is a Django setting; None disables it."""

    rate_setting = None

    def __init__(self):
        """Skip DRF's class-level rate table; the rate is read per request."""
        self.rate = self.get_rate()
        self.num_requests, self.duration = self.parse_rate(self.rate)

    def get_rate(self):
        """Return the configured rate, e.g. ``"1200/min"``, or None."""
        return getattr(settings, self.rate_setting, None) or None


class AccountRateThrottle(_SettingsRateThrottle):
    """Requests per account, across all of its credentials."""

    scope = "account"
    rate_setting = "API_RATE_LIMIT"

    def get_cache_key(self, request, view):
        """Key on the account; anonymous requests are not counted here."""
        if not (request.user and request.user.is_authenticated):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.user.pk}


class AnonymousRateThrottle(_SettingsRateThrottle):
    """Requests per client address for calls without credentials."""

    scope = "anonymous"
    rate_setting = "API_ANON_RATE_LIMIT"

    def get_cache_key(self, request, view):
        """Key on the client address; signed-in requests are not counted here."""
        if request.user and request.user.is_authenticated:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }
