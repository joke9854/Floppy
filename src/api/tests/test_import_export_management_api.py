"""FORK (P1-H): import runs, import and export schedules, Letterboxd export."""

import json
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from app.models import Movie
from integrations.models import ImportRun

from .base import FloppyApiTestCase


class ImportRunTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.run = ImportRun.objects.create(
            user=self.user1, source="trakt", task_id="task-1"
        )

    def _post(self, name, run_id=None):
        return self.call_api(
            "post", name, args=(run_id or self.run.id,), headers=self.auth_headers
        )

    def test_list_only_own_runs(self):
        ImportRun.objects.create(user=self.user2, source="mal")
        response = self.call_api("get", "api_import_runs", headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual([r["id"] for r in response.json()["results"]], [self.run.id])

    @patch("config.celery.app.control.revoke")
    def test_cancel_then_rollback(self, revoke):
        self.assertEqual(
            self._post("api_import_run_rollback").status_code, HTTP.CONFLICT
        )

        cancelled = self._post("api_import_run_cancel")

        self.assertEqual(cancelled.status_code, HTTP.OK)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        revoke.assert_called_once_with("task-1", terminate=True)
        self.assertEqual(self._post("api_import_run_cancel").status_code, HTTP.CONFLICT)

        movie = self.movie_medias[0]
        Movie.objects.filter(id=movie.id).update(import_run=self.run)
        rolled_back = self._post("api_import_run_rollback")
        self.assertEqual(rolled_back.status_code, HTTP.OK)
        self.assertGreaterEqual(rolled_back.json()["deleted"], 1)
        self.assertFalse(Movie.objects.filter(id=movie.id).exists())

    def test_other_users_run_is_404(self):
        other = ImportRun.objects.create(user=self.user2, source="mal")
        self.assertEqual(
            self._post("api_import_run_cancel", other.id).status_code, HTTP.NOT_FOUND
        )
        self.assertEqual(
            self._post("api_import_run_rollback", other.id).status_code,
            HTTP.NOT_FOUND,
        )


def _crontab():
    return CrontabSchedule.objects.create(minute="0", hour="3")


class ScheduleTests(FloppyApiTestCase):
    def test_import_schedule_ids_and_delete(self):
        mine = PeriodicTask.objects.create(
            name=f"Import from Radarr (Recurring) for {self.user1.username}",
            task="Import from Radarr (Recurring)",
            crontab=_crontab(),
            kwargs=json.dumps({"user_id": self.user1.id}),
        )
        # Same id prefix, other user: user 1 must not reach user 1x's schedule.
        other_user = get_user_model().objects.create_user(
            username="eleven", password="x", id=self.user1.id * 10 + 1
        )
        theirs = PeriodicTask.objects.create(
            name="Import from Radarr (Recurring) for eleven",
            task="Import from Radarr (Recurring)",
            crontab=_crontab(),
            kwargs=json.dumps({"user_id": other_user.id}),
        )

        delete = self.call_api(
            "delete",
            "api_import_schedule_detail",
            args=(theirs.id,),
            headers=self.auth_headers,
        )
        self.assertEqual(delete.status_code, HTTP.NOT_FOUND)
        self.assertTrue(PeriodicTask.objects.filter(id=theirs.id).exists())

        deleted = self.call_api(
            "delete",
            "api_import_schedule_detail",
            args=(mine.id,),
            headers=self.auth_headers,
        )
        self.assertEqual(deleted.json(), {"outcome": "deleted"})
        self.assertFalse(PeriodicTask.objects.filter(id=mine.id).exists())

    def test_export_schedules_create_list_delete(self):
        payload = {
            "frequency": "weekly",
            "time": "04:30",
            "media_types": ["movie"],
            "include_lists": True,
        }
        created = self.call_api(
            "post", "api_export_schedules", payload=payload, headers=self.auth_headers
        )
        self.assertEqual(created.status_code, HTTP.CREATED)
        schedule_id = created.json()["id"]
        self.assertEqual(created.json()["media_types"], ["movie"])

        duplicate = self.call_api(
            "post", "api_export_schedules", payload=payload, headers=self.auth_headers
        )
        self.assertEqual(duplicate.status_code, HTTP.BAD_REQUEST)

        listed = self.call_api(
            "get", "api_export_schedules", headers=self.auth_headers
        ).json()["results"]
        self.assertEqual([s["id"] for s in listed], [schedule_id])
        self.assertEqual(
            self.call_api(
                "get", "api_export_schedules", headers=self.auth_headers2
            ).json()["results"],
            [],
        )
        self.assertEqual(
            self.call_api(
                "delete",
                "api_export_schedule_detail",
                args=(schedule_id,),
                headers=self.auth_headers2,
            ).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self.call_api(
                "delete",
                "api_export_schedule_detail",
                args=(schedule_id,),
                headers=self.auth_headers,
            ).status_code,
            HTTP.NO_CONTENT,
        )

    def test_bad_export_schedules_are_400(self):
        for payload in (
            {"frequency": "hourly", "time": "04:30", "media_types": ["movie"]},
            {"frequency": "daily", "time": "25:00", "media_types": ["movie"]},
            {"frequency": "daily", "time": "04:30"},
            {"frequency": "daily", "time": "04:30", "media_types": ["nope"]},
        ):
            with self.subTest(payload=payload):
                response = self.call_api(
                    "post",
                    "api_export_schedules",
                    payload=payload,
                    headers=self.auth_headers,
                )
                self.assertEqual(response.status_code, HTTP.BAD_REQUEST)


class LetterboxdExportTests(FloppyApiTestCase):
    def test_streams_csv(self):
        response = self.call_api(
            "get", "api_export_letterboxd", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertTrue(b"".join(response.streaming_content))
