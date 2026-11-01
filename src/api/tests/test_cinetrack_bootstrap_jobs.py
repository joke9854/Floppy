"""CineTrack bootstrap jobs: large batches ensured on a worker, polled by id."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.db import OperationalError

from api import cinetrack_bootstrap_views
from api.tasks import MAX_BOOTSTRAP_JOB_ITEMS
from app.models import TV, Movie

from .base import FloppyApiTestCase


def _movies(count, start=9000):
    return [
        {"source": "tmdb", "media_id": str(start + index), "title": f"Movie {index}", "status": 3}
        for index in range(count)
    ]


class CineTrackBootstrapJobTests(FloppyApiTestCase):
    """CELERY_TASK_ALWAYS_EAGER runs the job inside the POST."""

    def _submit(self, payload):
        return self.call_api("post", "api_cinetrack_bootstrap_jobs", payload=payload, headers=self.auth_headers)

    def _poll(self, job_id, headers=None):
        return self.call_api(
            "get",
            "api_cinetrack_bootstrap_job_detail",
            args=[job_id],
            headers=headers or self.auth_headers,
        )

    def test_a_large_movie_batch_finishes_with_one_result_per_entry(self):
        response = self._submit({"movies": _movies(120)})

        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(response.json()["total"], 120)
        job = self._poll(response.json()["job_id"]).json()
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["processed"], 120)
        self.assertEqual([r["media_id"] for r in job["results"]], [str(9000 + i) for i in range(120)])
        self.assertEqual({r["status"] for r in job["results"]}, {"created"})
        ids = [str(9000 + i) for i in range(120)]
        self.assertEqual(Movie.objects.filter(user=self.user1, item__media_id__in=ids).count(), 120)

        again = self._poll(self._submit({"movies": _movies(120)}).json()["job_id"]).json()
        self.assertEqual({r["status"] for r in again["results"]}, {"already_satisfied"})

    def test_a_show_batch_runs_as_a_job(self):
        shows = [{"source": "tmdb", "media_id": "7101", "title": "Show", "status": 1}]

        job = self._poll(self._submit({"shows": shows}).json()["job_id"]).json()

        self.assertEqual(job["kind"], "shows")
        self.assertEqual(job["results"], [{"source": "tmdb", "media_id": "7101", "status": "created"}])
        self.assertTrue(TV.objects.filter(user=self.user1, item__media_id="7101").exists())

    def test_malformed_batches_are_rejected_before_a_job_exists(self):
        cases = {
            "neither kind": {},
            "both kinds": {"movies": _movies(1), "shows": []},
            "oversized": {"movies": _movies(MAX_BOOTSTRAP_JOB_ITEMS + 1)},
            "invalid entry": {"movies": [{"source": "tmdb", "media_id": "", "status": 3}]},
        }
        for name, payload in cases.items():
            with self.subTest(name), patch("api.cinetrack_bootstrap_job_views.run_cinetrack_bootstrap_job") as task:
                response = self._submit(payload)

                self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
                self.assertEqual(response.json()["code"], "bad_request")
                task.delay.assert_not_called()

    def test_a_job_is_visible_only_to_its_owner(self):
        job_id = self._submit({"movies": _movies(1)}).json()["job_id"]

        other = self._poll(job_id, headers={"HTTP_X_API_KEY": self.user2.token})
        unknown = self._poll("0" * 32)

        self.assertEqual(other.status_code, HTTP.NOT_FOUND)
        self.assertEqual(unknown.status_code, HTTP.NOT_FOUND)

    def test_a_failed_chunk_reports_error_and_the_others_keep_their_outcomes(self):
        real = cinetrack_bootstrap_views.ensure_movie_entries
        calls = []

        def fail_second_chunk(user, parsed, **kwargs):
            calls.append(len(parsed))
            if len(calls) == 2:
                raise RuntimeError("boom")
            return real(user, parsed, **kwargs)

        with patch.object(cinetrack_bootstrap_views, "ensure_movie_entries", side_effect=fail_second_chunk):
            job = self._poll(self._submit({"movies": _movies(120)}).json()["job_id"]).json()

        statuses = [r["status"] for r in job["results"]]
        self.assertEqual(calls, [50, 50, 20])
        self.assertEqual(statuses, ["created"] * 50 + ["error"] * 50 + ["created"] * 20)

    def test_a_locked_database_is_retried_on_the_worker(self):
        real = cinetrack_bootstrap_views.ensure_movie_entries
        attempts = []

        def locked_once(user, parsed, **kwargs):
            attempts.append(1)
            if len(attempts) == 1:
                raise OperationalError("database is locked")
            return real(user, parsed, **kwargs)

        with (
            patch.object(cinetrack_bootstrap_views, "ensure_movie_entries", side_effect=locked_once),
            patch("api.tasks.time.sleep") as sleep,
        ):
            job = self._poll(self._submit({"movies": _movies(2)}).json()["job_id"]).json()

        self.assertEqual([r["status"] for r in job["results"]], ["created", "created"])
        sleep.assert_called_once_with(1)

    def test_a_queue_failure_answers_503_and_leaves_no_job(self):
        with patch("api.cinetrack_bootstrap_job_views.run_cinetrack_bootstrap_job") as task:
            task.delay.side_effect = OSError("broker down")
            response = self._submit({"movies": _movies(1)})

        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)

    def test_the_capability_is_advertised(self):
        info = self.call_api("get", "api_info").json()

        self.assertIs(info["api_extensions"]["cinetrack_bootstrap_jobs_v1"], True)
