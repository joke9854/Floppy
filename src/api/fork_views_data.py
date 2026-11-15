"""Import runs, import and export schedules, Letterboxd export (P1-H).

The web's Import and Export settings: cancel or undo an import run, remove a
recurring import, create or remove recurring backups. The changes live in
`users.data_management`, shared with the web views.
"""

import json
from http import HTTPStatus as HTTP  # noqa: N814

from django.http import StreamingHttpResponse
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from app.models import MediaTypes
from integrations import exports
from integrations.models import ImportRun
from users import data_management, helpers

from .contract_serializers import DetailErrorSerializer

RUNS_LIMIT = 50


class ImportRunRecordSerializer(serializers.Serializer):
    """One import run."""

    id = serializers.IntegerField()
    source = serializers.CharField()
    status = serializers.ChoiceField(choices=ImportRun.Status.values)
    created_count = serializers.IntegerField()
    updated_count = serializers.IntegerField()
    skipped_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    remaining_estimate = serializers.IntegerField(allow_null=True)
    started_at = serializers.DateTimeField()
    finished_at = serializers.DateTimeField(allow_null=True)


class ImportRunListSerializer(serializers.Serializer):
    """Recent import runs, newest first."""

    results = ImportRunRecordSerializer(many=True)


class ImportRollbackSerializer(serializers.Serializer):
    """What the undo removed."""

    deleted = serializers.IntegerField(help_text="Rows removed.")
    reverted = serializers.IntegerField(help_text="Music plays taken back.")


class ImportScheduleDeletedSerializer(serializers.Serializer):
    """How the schedule was removed."""

    outcome = serializers.ChoiceField(
        choices=["deleted", "disconnected_lastfm"],
        help_text=(
            "`disconnected_lastfm`: Last.fm polls every account from one shared "
            "schedule, so removing it disconnects this account's Last.fm."
        ),
    )


def _run_payload(run):
    return {
        "id": run.id,
        "source": run.source,
        "status": run.status,
        "created_count": run.created_count,
        "updated_count": run.updated_count,
        "skipped_count": run.skipped_count,
        "failed_count": run.failed_count,
        "remaining_estimate": run.remaining_estimate,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
    }


def _own_run(request, run_id):
    return ImportRun.objects.filter(id=run_id, user=request.user).first()


_RUN_NOT_FOUND = {"detail": "Import run not found."}


class ImportRunsView(drf_views.APIView):
    """Recent import runs, which can be cancelled or undone."""

    @extend_schema(
        operation_id="listImportRuns",
        responses={200: ImportRunListSerializer},
    )
    def get(self, request):
        """Return the latest runs, newest first."""
        runs = ImportRun.objects.filter(user=request.user).order_by("-started_at")[
            :RUNS_LIMIT
        ]
        return Response(
            {"results": [_run_payload(run) for run in runs]},
            status=HTTP.OK,
        )


class ImportRunCancelView(drf_views.APIView):
    """Stop a running import."""

    @extend_schema(
        operation_id="cancelImportRun",
        request=None,
        responses={
            200: ImportRunRecordSerializer,
            404: DetailErrorSerializer,
            409: OpenApiResponse(DetailErrorSerializer, description="Not running."),
        },
    )
    def post(self, request, run_id):
        """Cancel the run and return it."""
        run = _own_run(request, run_id)
        if run is None:
            return Response(_RUN_NOT_FOUND, status=HTTP.NOT_FOUND)
        try:
            data_management.cancel_import_run(run)
        except data_management.DataManagementError as error:
            return Response(
                {"detail": str(error), "code": "conflict"}, status=HTTP.CONFLICT
            )
        run.refresh_from_db()
        return Response(_run_payload(run), status=HTTP.OK)


class ImportRunRollbackView(drf_views.APIView):
    """Undo what one import run added."""

    @extend_schema(
        operation_id="rollbackImportRun",
        request=None,
        responses={
            200: ImportRollbackSerializer,
            404: DetailErrorSerializer,
            409: OpenApiResponse(
                DetailErrorSerializer,
                description="Still running; cancel it first.",
            ),
        },
    )
    def post(self, request, run_id):
        """Remove the run's rows and take back its music plays."""
        run = _own_run(request, run_id)
        if run is None:
            return Response(_RUN_NOT_FOUND, status=HTTP.NOT_FOUND)
        try:
            deleted, reverted = data_management.rollback_import_run(run, request.user)
        except data_management.DataManagementError as error:
            return Response(
                {"detail": str(error), "code": "conflict"}, status=HTTP.CONFLICT
            )
        return Response({"deleted": deleted, "reverted": reverted}, status=HTTP.OK)


class ImportScheduleDetailView(drf_views.APIView):
    """Remove one recurring import, by the `id` from imports/activity."""

    @extend_schema(
        operation_id="deleteImportSchedule",
        responses={200: ImportScheduleDeletedSerializer, 404: DetailErrorSerializer},
    )
    def delete(self, request, schedule_id):
        """Delete the schedule (or disconnect Last.fm, see `outcome`)."""
        task = PeriodicTask.objects.filter(id=schedule_id).first()
        if task is None:
            return Response(
                {"detail": "Import schedule not found."}, status=HTTP.NOT_FOUND
            )
        try:
            outcome = data_management.delete_import_schedule(request.user, task)
        except data_management.DataManagementError as error:
            return Response({"detail": str(error)}, status=HTTP.NOT_FOUND)
        return Response({"outcome": outcome}, status=HTTP.OK)


# --- /api/v1/exports/schedules/ ---------------------------------------------


class ExportScheduleSerializer(serializers.Serializer):
    """A recurring backup export."""

    id = serializers.IntegerField()
    frequency = serializers.CharField(allow_null=True)
    next_run = serializers.DateTimeField(allow_null=True)
    last_run = serializers.DateTimeField(allow_null=True)
    media_types = serializers.ListField(child=serializers.CharField())
    include_lists = serializers.BooleanField()
    include_collection = serializers.BooleanField()


class ExportScheduleListSerializer(serializers.Serializer):
    """The user's recurring backups."""

    results = ExportScheduleSerializer(many=True)


class ExportScheduleCreateSerializer(serializers.Serializer):
    """A new recurring backup."""

    frequency = serializers.ChoiceField(choices=list(data_management.EXPORT_FREQUENCIES))
    time = serializers.CharField(help_text="Time of day, `HH:MM`, server time zone.")
    media_types = serializers.ListField(child=serializers.CharField(), required=False)
    include_lists = serializers.BooleanField(required=False)
    include_collection = serializers.BooleanField(required=False)


def _export_payload(task):
    kwargs = json.loads(task.kwargs or "{}")
    info = helpers.get_next_run_info(task) or {}
    return {
        "id": task.id,
        "frequency": info.get("frequency"),
        "next_run": info.get("next_run"),
        "last_run": task.last_run_at,
        "media_types": list(kwargs.get("media_types") or []),
        "include_lists": bool(kwargs.get("include_lists")),
        "include_collection": bool(kwargs.get("include_collection")),
    }


class ExportSchedulesView(drf_views.APIView):
    """List or create recurring backup exports."""

    @extend_schema(
        operation_id="listExportSchedules",
        responses={200: ExportScheduleListSerializer},
    )
    def get(self, request):
        """Return the recurring backups."""
        return Response(
            {
                "results": [
                    _export_payload(task)
                    for task in data_management.export_schedules_for(request.user)
                ],
            },
            status=HTTP.OK,
        )

    @extend_schema(
        operation_id="createExportSchedule",
        request=ExportScheduleCreateSerializer,
        responses={
            201: ExportScheduleSerializer,
            400: DetailErrorSerializer,
            403: OpenApiResponse(
                DetailErrorSerializer, description="Demo accounts are view-only."
            ),
        },
    )
    def post(self, request):
        """Create the schedule; the first backup runs at the next slot."""
        if request.user.is_demo:
            return Response(
                {"detail": "This section is view-only for demo accounts."},
                status=HTTP.FORBIDDEN,
            )
        data = request.data if isinstance(request.data, dict) else {}
        media_types = data.get("media_types") or []
        include_lists = data.get("include_lists", False)
        include_collection = data.get("include_collection", False)
        if (
            not isinstance(media_types, list)
            or any(value not in MediaTypes.values for value in media_types)
            or not isinstance(include_lists, bool)
            or not isinstance(include_collection, bool)
        ):
            return Response(
                {
                    "detail": (
                        "media_types must be a list of media types; include_lists "
                        "and include_collection must be booleans."
                    ),
                },
                status=HTTP.BAD_REQUEST,
            )
        try:
            task = data_management.create_export_schedule(
                request.user,
                frequency=str(data.get("frequency") or ""),
                export_time=str(data.get("time") or ""),
                media_types=media_types,
                include_lists=include_lists,
                include_collection=include_collection,
            )
        except data_management.DataManagementError as error:
            return Response({"detail": str(error)}, status=HTTP.BAD_REQUEST)
        return Response(_export_payload(task), status=HTTP.CREATED)


class ExportScheduleDetailView(drf_views.APIView):
    """Remove one recurring backup."""

    @extend_schema(
        operation_id="deleteExportSchedule",
        responses={204: None, 404: DetailErrorSerializer},
    )
    def delete(self, request, schedule_id):
        """Delete the schedule; backups already written stay."""
        task = PeriodicTask.objects.filter(id=schedule_id).first()
        if task is None or not data_management.delete_export_schedule(
            request.user, task
        ):
            return Response(
                {"detail": "Backup schedule not found."}, status=HTTP.NOT_FOUND
            )
        return Response(status=HTTP.NO_CONTENT)


class ExportLetterboxdView(drf_views.APIView):
    """Download watched movies as a Letterboxd import CSV."""

    @extend_schema(
        operation_id="exportLetterboxdCsv",
        responses={(200, "text/csv"): OpenApiTypes.STR},
    )
    def get(self, request):
        """Stream the CSV."""
        now = timezone.localtime()
        return StreamingHttpResponse(
            streaming_content=exports.generate_letterboxd_rows(request.user),
            content_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="letterboxd_{now}.csv"',
            },
        )
