"""CineTrack crash/ANR report upload to the user's own Floppy server.

Reports are sanitized by the client. The server never logs the stack trace,
request body or credentials.
"""

from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework import views as drf_views
from rest_framework.response import Response

from users.models import CineTrackCrashReport

from .contract_serializers import DetailErrorSerializer
from .throttling import (
    AccountRateThrottle,
    AnonymousRateThrottle,
    CrashReportRateThrottle,
)

MAX_REPORTS_PER_USER = 500
MAX_STACK_TRACE_CHARS = 65536


class _AwareDateTimeField(serializers.DateTimeField):
    """Datetime that must carry an explicit offset; never guess a timezone."""

    def enforce_timezone(self, value):
        """Reject naive datetimes instead of assuming the server timezone."""
        if value.tzinfo is None or value.utcoffset() is None:
            self.fail("make_aware", timezone="an explicit offset")
        return value


class CineTrackCrashReportSerializer(serializers.Serializer):
    """Sanitized crash or ANR report."""

    report_id = serializers.UUIDField(help_text="Client-generated idempotency key.")
    kind = serializers.ChoiceField(choices=["crash", "anr"])
    occurred_at = _AwareDateTimeField(
        help_text="ISO-8601 datetime with timezone; stored exactly."
    )
    app_version = serializers.CharField(max_length=64)
    version_code = serializers.IntegerField(min_value=0)
    build_type = serializers.CharField(max_length=32)
    android_sdk = serializers.IntegerField()
    device_model = serializers.CharField(max_length=128)
    exception_class = serializers.CharField(
        max_length=256, required=False, allow_blank=True
    )
    thread = serializers.CharField(max_length=128, required=False, allow_blank=True)
    stack_trace = serializers.CharField(max_length=MAX_STACK_TRACE_CHARS)


class CineTrackCrashReportResultSerializer(serializers.Serializer):
    """Outcome of a crash-report upload."""

    report_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["created", "already_received"])


class CineTrackCrashReportView(drf_views.APIView):
    """Accept one sanitized crash or ANR report per request."""

    required_scopes = {"POST": "watchlist:write"}
    throttle_classes = [
        AccountRateThrottle,
        AnonymousRateThrottle,
        CrashReportRateThrottle,
    ]

    @extend_schema(
        request=CineTrackCrashReportSerializer,
        responses={
            200: OpenApiResponse(
                CineTrackCrashReportResultSerializer,
                description="Report id was already received; nothing changed.",
            ),
            201: OpenApiResponse(
                CineTrackCrashReportResultSerializer,
                description="Report stored.",
            ),
            400: OpenApiResponse(
                DetailErrorSerializer, description="Invalid report fields."
            ),
            401: OpenApiResponse(
                DetailErrorSerializer, description="Missing or invalid API key."
            ),
            403: OpenApiResponse(
                DetailErrorSerializer,
                description="Token lacks the watchlist:write scope.",
            ),
            429: OpenApiResponse(
                DetailErrorSerializer, description="Too many crash reports."
            ),
        },
    )
    def post(self, request):
        """Store a crash report once per (account, report_id)."""
        serializer = CineTrackCrashReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report_id = str(data["report_id"])

        if CineTrackCrashReport.objects.filter(
            user=request.user, report_id=data["report_id"]
        ).exists():
            return Response({"report_id": report_id, "status": "already_received"})

        try:
            with transaction.atomic():
                CineTrackCrashReport.objects.create(user=request.user, **data)
        except IntegrityError:
            # Concurrent retry of the same report id.
            return Response({"report_id": report_id, "status": "already_received"})

        keep = list(
            CineTrackCrashReport.objects.filter(user=request.user)
            .order_by("-received_at", "-pk")
            .values_list("pk", flat=True)[:MAX_REPORTS_PER_USER]
        )
        CineTrackCrashReport.objects.filter(user=request.user).exclude(
            pk__in=keep
        ).delete()

        return Response(
            {"report_id": report_id, "status": "created"},
            status=status.HTTP_201_CREATED,
        )
