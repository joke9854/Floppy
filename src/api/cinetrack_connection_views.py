"""CineTrack-specific authenticated connection probe.

The probe is intentionally constant-cost: it authenticates the caller and
returns only local server/account/capability information. It must never scan
tracking data or contact metadata providers.
"""

from django.core.signing import salted_hmac
from rest_framework import views as drf_views
from rest_framework.response import Response

from .serializers import InfoSerializer, serialize_data


CINETRACK_API_EXTENSIONS = {
    "cinetrack_episode_events_v1": True,
    "cinetrack_bootstrap_v2": True,
    "episode_sql_pagination": True,
}


class CineTrackConnectionView(drf_views.APIView):
    """Authenticate a CineTrack tracking client without reading preferences."""

    # Keep the requirement explicit as well as present in VIEW_SCOPES. This makes
    # the contract self-documenting and prevents a future map refactor from
    # accidentally widening this endpoint to arbitrary authenticated scopes.
    required_scopes = {"GET": "watchlist:read"}

    def get(self, request):
        """Return safe identity and capability information for this remote."""
        info = serialize_data({}, serializer_class=InfoSerializer)
        account_id = salted_hmac(
            "api.cinetrack.connection.account.v1",
            str(request.user.pk),
        ).hexdigest()

        return Response(
            {
                "authenticated": True,
                "account_id": account_id,
                # Temporary compatibility alias for Android clients that used
                # the old preferences response solely to derive an account
                # identity. This value is the same opaque HMAC, never a username.
                "user": account_id,
                "server_version": info.get("version"),
                "api_extensions": dict(CINETRACK_API_EXTENSIONS),
            }
        )
