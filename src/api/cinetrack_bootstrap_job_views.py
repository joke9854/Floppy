"""CineTrack bootstrap jobs: submit a large batch once, poll for the outcomes.

The synchronous ensure endpoints take 50 items per request and wait for
SQLite's single writer in the request thread. A job takes up to
``MAX_BOOTSTRAP_JOB_ITEMS`` and runs the same ensure code on a Celery worker.
The client acknowledges entries only from a finished job's results.
"""

import logging
import uuid
from http import HTTPStatus as HTTP  # noqa: N814

from django.core.cache import cache
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers
from rest_framework import views as drf_views
from rest_framework.response import Response

from .cinetrack_bootstrap_views import (
    CineTrackBootstrapResultSerializer,
    CineTrackMovieInputSerializer,
    CineTrackShowInputSerializer,
    parse_movie_entries,
    parse_show_entries,
)
from .contract_serializers import DetailErrorSerializer
from .tasks import (
    BOOTSTRAP_JOB_TTL_SECONDS,
    MAX_BOOTSTRAP_JOB_ITEMS,
    bootstrap_job_key,
    run_cinetrack_bootstrap_job,
)

logger = logging.getLogger(__name__)
_PARSERS = {"movies": parse_movie_entries, "shows": parse_show_entries}


class CineTrackBootstrapJobRequestSerializer(serializers.Serializer):
    """Exactly one of ``movies`` or ``shows``."""

    movies = CineTrackMovieInputSerializer(many=True, required=False)
    shows = CineTrackShowInputSerializer(many=True, required=False)


class CineTrackBootstrapJobResultSerializer(CineTrackBootstrapResultSerializer):
    """A job result; ``error`` means this entry's outcome is unknown, resubmit it."""

    status = serializers.ChoiceField(choices=("created", "already_satisfied", "error"))


class CineTrackBootstrapJobSerializer(serializers.Serializer):
    """A job's state. ``results`` is present once ``status`` is ``done``."""

    job_id = serializers.CharField()
    kind = serializers.ChoiceField(choices=("movies", "shows"))
    status = serializers.ChoiceField(choices=("queued", "running", "done"))
    total = serializers.IntegerField()
    processed = serializers.IntegerField()
    results = CineTrackBootstrapJobResultSerializer(many=True, required=False)


def _public(job_id, job):
    body = {key: job[key] for key in ("kind", "status", "total", "processed")}
    if "results" in job:
        body["results"] = job["results"]
    return {"job_id": job_id, **body}


class CineTrackBootstrapJobsView(drf_views.APIView):
    """Accept a large movies or shows batch as a background job."""

    required_scopes = {"POST": "watchlist:write"}

    @extend_schema(
        request=CineTrackBootstrapJobRequestSerializer,
        responses={
            202: CineTrackBootstrapJobSerializer,
            400: OpenApiResponse(DetailErrorSerializer, description="Malformed or oversized batch; no job was created."),
            503: OpenApiResponse(DetailErrorSerializer, description="The job could not be queued; retry later."),
        },
    )
    def post(self, request):
        """Queue a bootstrap job."""
        kinds = [kind for kind in _PARSERS if kind in request.data]
        if len(kinds) != 1:
            return Response({"detail": "Send exactly one of movies or shows."}, status=HTTP.BAD_REQUEST)
        kind = kinds[0]
        parsed, error = _PARSERS[kind](request.data[kind], max_items=MAX_BOOTSTRAP_JOB_ITEMS)
        if error:
            return Response({"detail": error}, status=HTTP.BAD_REQUEST)

        job_id = uuid.uuid4().hex
        key = bootstrap_job_key(request.user.pk, job_id)
        job = {"kind": kind, "status": "queued", "total": len(parsed), "processed": 0, "entries": parsed}
        cache.set(key, job, BOOTSTRAP_JOB_TTL_SECONDS)
        try:
            run_cinetrack_bootstrap_job.delay(request.user.pk, job_id)
        except Exception:
            logger.exception("Could not queue CineTrack bootstrap job")
            cache.delete(key)
            return Response(
                {"detail": "The job could not be queued; retry later."},
                status=HTTP.SERVICE_UNAVAILABLE,
            )
        return Response(_public(job_id, job), status=HTTP.ACCEPTED)


class CineTrackBootstrapJobDetailView(drf_views.APIView):
    """Report a bootstrap job's progress and, once done, its results."""

    required_scopes = {"GET": "watchlist:read"}

    @extend_schema(
        responses={
            200: CineTrackBootstrapJobSerializer,
            404: OpenApiResponse(DetailErrorSerializer, description="Unknown or expired job; resubmit the batch."),
        },
    )
    def get(self, request, job_id):
        """Return a bootstrap job's state."""
        job = cache.get(bootstrap_job_key(request.user.pk, job_id))
        if job is None:
            return Response({"detail": "Unknown or expired job."}, status=HTTP.NOT_FOUND)
        return Response(_public(job_id, job), status=HTTP.OK)
