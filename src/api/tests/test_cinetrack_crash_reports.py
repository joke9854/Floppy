"""Tests for the CineTrack crash/ANR report upload endpoint."""

import uuid
from datetime import UTC, datetime
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from integrations.models import IntegrationToken
from users.models import CineTrackCrashReport

from .base import FloppyApiTestCase

URL = "/api/v1/cinetrack/crash-reports/"


def payload(**overrides):
    """Return a valid report body."""
    body = {
        "report_id": str(uuid.uuid4()),
        "kind": "crash",
        "occurred_at": "2026-10-17T12:34:56.789123+02:00",
        "app_version": "0.99.64",
        "version_code": 9964,
        "build_type": "release",
        "android_sdk": 34,
        "device_model": "Pixel 8",
        "exception_class": "java.lang.IllegalStateException",
        "thread": "main",
        "stack_trace": "java.lang.IllegalStateException: boom\n\tat a.b(C.kt:1)",
    }
    body.update(overrides)
    return body


class CineTrackCrashReportTests(FloppyApiTestCase):
    """Create, idempotency, validation, scope and retention behavior."""

    def setUp(self):
        super().setUp()
        _, raw = IntegrationToken.generate(user=self.user1, name="CineTrack")
        self.headers = {"HTTP_X_API_KEY": raw}

    def post(self, body, headers=None):
        """POST a JSON report."""
        return self.client.post(
            URL,
            data=body,
            content_type="application/json",
            **(headers or self.headers),
        )

    def test_create_persists_exact_occurred_at(self):
        body = payload()
        response = self.post(body)
        self.assertEqual(response.status_code, HTTP.CREATED)
        self.assertEqual(
            response.json(), {"report_id": body["report_id"], "status": "created"}
        )
        row = CineTrackCrashReport.objects.get(user=self.user1)
        self.assertEqual(
            row.occurred_at,
            datetime(2026, 10, 17, 10, 34, 56, 789123, tzinfo=UTC),
        )
        self.assertEqual(row.stack_trace, body["stack_trace"])

    def test_retry_is_idempotent_and_does_not_modify_row(self):
        body = payload()
        self.assertEqual(self.post(body).status_code, HTTP.CREATED)
        retry = self.post(payload(report_id=body["report_id"], app_version="other"))
        self.assertEqual(retry.status_code, HTTP.OK)
        self.assertEqual(retry.json()["status"], "already_received")
        self.assertEqual(CineTrackCrashReport.objects.count(), 1)
        self.assertEqual(CineTrackCrashReport.objects.get().app_version, "0.99.64")

    def test_other_user_same_report_id_gets_own_row(self):
        body = payload()
        self.assertEqual(self.post(body).status_code, HTTP.CREATED)
        _, raw = IntegrationToken.generate(user=self.user2, name="Other")
        other = self.post(body, {"HTTP_X_API_KEY": raw})
        self.assertEqual(other.status_code, HTTP.CREATED)
        self.assertEqual(CineTrackCrashReport.objects.count(), 2)

    def test_optional_fields_may_be_omitted(self):
        body = payload(kind="anr")
        del body["exception_class"]
        del body["thread"]
        self.assertEqual(self.post(body).status_code, HTTP.CREATED)

    def test_missing_and_invalid_fields_are_rejected(self):
        cases = {
            "report_id": [None, "not-a-uuid"],
            "kind": ["freeze"],
            "occurred_at": ["yesterday", "2026-10-17T12:00:00"],
            "version_code": [-1, "x"],
            "android_sdk": ["x"],
            "app_version": ["v" * 65],
            "stack_trace": [None],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    response = self.post(payload(**{field: value}))
                    self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
                    self.assertIn(field, response.json())
        for field in payload():
            if field in {"exception_class", "thread"}:
                continue
            with self.subTest(missing=field):
                body = payload()
                del body[field]
                response = self.post(body)
                self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
                self.assertIn(field, response.json())
        self.assertEqual(CineTrackCrashReport.objects.count(), 0)

    def test_stack_trace_length_limit(self):
        ok = self.post(payload(stack_trace="x" * 65536))
        self.assertEqual(ok.status_code, HTTP.CREATED)
        too_long = self.post(payload(stack_trace="x" * 65537))
        self.assertEqual(too_long.status_code, HTTP.BAD_REQUEST)
        self.assertIn("stack_trace", too_long.json())

    def test_missing_scope_is_forbidden(self):
        _, raw = IntegrationToken.generate(
            user=self.user1, name="Read only", scopes=["watchlist:read"]
        )
        response = self.post(payload(), {"HTTP_X_API_KEY": raw})
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertEqual(CineTrackCrashReport.objects.count(), 0)

    def test_unauthenticated_is_rejected(self):
        # This API answers invalid or absent credentials with 403 (see
        # test_cinetrack_connection.test_probe_rejects_invalid_credentials).
        for headers in ({}, {"HTTP_X_API_KEY": "flp_invalid_crash_token"}):
            response = self.post(payload(), headers or {"HTTP_ACCEPT": "*/*"})
            self.assertIn(response.status_code, {HTTP.UNAUTHORIZED, HTTP.FORBIDDEN})
        self.assertEqual(CineTrackCrashReport.objects.count(), 0)

    def test_retention_prunes_only_this_users_oldest_reports(self):
        for _ in range(2):
            CineTrackCrashReport.objects.create(
                user=self.user2,
                **{k: v for k, v in payload().items() if k != "report_id"},
                report_id=uuid.uuid4(),
            )
        with patch("api.cinetrack_crash_report_views.MAX_REPORTS_PER_USER", 3):
            ids = [payload()["report_id"] for _ in range(5)]
            for report_id in ids:
                response = self.post(payload(report_id=report_id))
                self.assertEqual(response.status_code, HTTP.CREATED)
        kept = set(
            CineTrackCrashReport.objects.filter(user=self.user1).values_list(
                "report_id", flat=True
            )
        )
        self.assertEqual({str(i) for i in kept}, set(ids[-3:]))
        self.assertEqual(CineTrackCrashReport.objects.filter(user=self.user2).count(), 2)

    def test_capability_is_advertised(self):
        info = self.client.get("/api/v1/info/", **self.headers).json()
        self.assertIs(info["api_extensions"]["cinetrack_crash_reports_v1"], True)
        probe = self.client.get("/api/v1/cinetrack/connection/", **self.headers).json()
        self.assertIs(probe["api_extensions"]["cinetrack_crash_reports_v1"], True)
