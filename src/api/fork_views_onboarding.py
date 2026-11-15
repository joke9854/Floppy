"""First-run setup wizard state through the API (P1-G).

The web wizard (`users.onboarding_views`) is a page flow; a client builds its
own flow from this state. Choosing media types is `PUT user/sidebar/`, and
connecting a service uses that service's own import endpoint.
"""

from http import HTTPStatus as HTTP  # noqa: N814

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from integrations.onboarding import ONBOARDING_SOURCES, get_source
from users.models import OnboardingStatusChoices, OnboardingStepChoices
from users.onboarding_views import _remaining_integrations, _remaining_sources

from .contract_serializers import DetailErrorSerializer

_SOURCE_LIST_FIELDS = (
    "selected_sources",
    "skipped_sources",
    "skipped_integrations",
)


class OnboardingSourceSerializer(serializers.Serializer):
    """An import source the wizard can offer."""

    slug = serializers.CharField()
    media_types = serializers.ListField(child=serializers.CharField())
    setup_kind = serializers.CharField(
        help_text="`oauth`, `api_key`, `host_url`, `credentials` or `upload`.",
    )
    connected = serializers.BooleanField()
    has_integration = serializers.BooleanField(
        help_text="Has a realtime integration (such as a webhook) to set up too.",
    )
    integration_configured = serializers.BooleanField()


class OnboardingStateSerializer(serializers.Serializer):
    """Where the user is in the setup wizard."""

    status = serializers.CharField()
    step = serializers.CharField()
    selected_sources = serializers.ListField(child=serializers.CharField())
    skipped_sources = serializers.ListField(child=serializers.CharField())
    connected_sources = serializers.ListField(child=serializers.CharField())
    skipped_integrations = serializers.ListField(child=serializers.CharField())
    remaining_sources = serializers.ListField(
        child=serializers.CharField(),
        help_text="Selected sources still to connect, in order.",
    )
    remaining_integrations = serializers.ListField(
        child=serializers.CharField(),
        help_text="Connected sources whose realtime integration is not set up.",
    )
    sources = OnboardingSourceSerializer(many=True)
    choices = serializers.DictField(child=serializers.ListField(child=serializers.CharField()))


class OnboardingUpdateSerializer(serializers.Serializer):
    """Fields to change; omitted fields keep their value."""

    status = serializers.CharField(required=False)
    step = serializers.CharField(required=False)
    selected_sources = serializers.ListField(child=serializers.CharField(), required=False)
    skipped_sources = serializers.ListField(child=serializers.CharField(), required=False)
    skipped_integrations = serializers.ListField(
        child=serializers.CharField(), required=False
    )


def _state(user):
    return {
        "status": user.onboarding_status,
        "step": user.onboarding_step,
        "selected_sources": list(user.onboarding_selected_sources or []),
        "skipped_sources": list(user.onboarding_skipped_sources or []),
        "connected_sources": list(user.onboarding_connected_sources or []),
        "skipped_integrations": list(user.onboarding_skipped_integrations or []),
        "remaining_sources": [source.slug for source in _remaining_sources(user)],
        "remaining_integrations": [
            source.slug for source in _remaining_integrations(user)
        ],
        "sources": [
            {
                "slug": source.slug,
                "media_types": list(source.media_types),
                "setup_kind": source.setup_kind,
                "connected": bool(source.is_connected(user)),
                "has_integration": bool(source.has_integration()),
                "integration_configured": bool(
                    source.has_integration() and source.is_integration_configured(user)
                ),
            }
            for source in ONBOARDING_SOURCES
        ],
        "choices": {
            "status": list(OnboardingStatusChoices.values),
            "step": list(OnboardingStepChoices.values),
        },
    }


class OnboardingView(drf_views.APIView):
    """Read or update the setup wizard state."""

    @extend_schema(
        operation_id="getOnboarding",
        responses={200: OnboardingStateSerializer},
    )
    def get(self, request):
        """Return the wizard state and the sources it can offer."""
        return Response(_state(request.user), status=HTTP.OK)

    @extend_schema(
        operation_id="updateOnboarding",
        request=OnboardingUpdateSerializer,
        responses={
            200: OnboardingStateSerializer,
            400: DetailErrorSerializer,
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="Guided setup is not available for demo accounts.",
            ),
        },
    )
    def patch(self, request):
        """Save the fields sent, after checking each against the known values."""
        user = request.user
        if user.is_demo:
            return Response(
                {"detail": "Guided setup isn't available for demo accounts."},
                status=HTTP.FORBIDDEN,
            )
        data = request.data if isinstance(request.data, dict) else {}
        updates = {}
        for field, choices in (
            ("status", OnboardingStatusChoices.values),
            ("step", OnboardingStepChoices.values),
        ):
            if field in data:
                if data[field] not in choices:
                    return Response(
                        {"detail": f"{field} must be one of {', '.join(choices)}."},
                        status=HTTP.BAD_REQUEST,
                    )
                updates[f"onboarding_{field}"] = data[field]
        for field in _SOURCE_LIST_FIELDS:
            if field not in data:
                continue
            slugs = data[field]
            if not isinstance(slugs, list) or not all(
                isinstance(slug, str) and get_source(slug) for slug in slugs
            ):
                return Response(
                    {"detail": f"{field} must be a list of known source slugs."},
                    status=HTTP.BAD_REQUEST,
                )
            updates[f"onboarding_{field}"] = sorted(set(slugs))
        if updates:
            for field, value in updates.items():
                setattr(user, field, value)
            user.save(update_fields=list(updates))
        return Response(_state(user), status=HTTP.OK)
