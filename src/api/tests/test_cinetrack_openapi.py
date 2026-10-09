"""The CineTrack endpoints are fully described in the dynamic OpenAPI schema."""

from django.urls import reverse

from .base import FloppyApiTestCase

CONNECTION = "/api/v1/cinetrack/connection/"
MOVIES = "/api/v1/cinetrack/bootstrap/movies/ensure/"
SHOWS = "/api/v1/cinetrack/bootstrap/shows/ensure/"
EPISODES = "/api/v1/media/{media_type}/{source}/{media_id}/episodes/ensure/"


class CineTrackOpenApiTests(FloppyApiTestCase):
    """Request, success and error shapes are published for CineTrack routes."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.schema = None

    def _schema(self):
        if self.schema is None:
            response = self.client.get(
                reverse("schema"), HTTP_ACCEPT="application/json"
            )
            self.assertEqual(response.status_code, 200)
            type(self).schema = response.json()
        return self.schema

    def _component(self, ref):
        return self._schema()["components"]["schemas"][ref.rsplit("/", 1)[-1]]

    def test_connection_probe_documents_identity_and_capabilities(self):
        responses = self._schema()["paths"][CONNECTION]["get"]["responses"]

        self.assertEqual({"200", "401", "403"}, set(responses))
        body = self._component(
            responses["200"]["content"]["application/json"]["schema"]["$ref"]
        )
        self.assertTrue(
            {"authenticated", "account_id", "server_version", "api_extensions"}
            <= set(body["properties"])
        )

    def test_v2_endpoints_document_request_success_and_errors(self):
        for path in (MOVIES, SHOWS, EPISODES):
            with self.subTest(path=path):
                operation = self._schema()["paths"][path]["post"]
                self.assertIn("requestBody", operation)
                self.assertEqual(
                    {"200", "400", "404", "409", "500"}, set(operation["responses"])
                )
                error = operation["responses"]["400"]["content"]["application/json"][
                    "schema"
                ]["$ref"]
                self.assertIn("detail", self._component(error)["properties"])
