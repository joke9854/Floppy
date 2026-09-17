"""Focused regression tests for CineTrack's constant-cost connection probe."""

from http import HTTPStatus as HTTP  # noqa: N814

from integrations.models import IntegrationToken

from .base import FloppyApiTestCase


class CineTrackConnectionTests(FloppyApiTestCase):
    """A tracking-scoped token must connect without user preference access."""

    def setUp(self):
        super().setUp()
        self.token, self.raw_token = IntegrationToken.generate(
            user=self.user1,
            name="CineTrack",
        )
        self.headers = {"HTTP_X_API_KEY": self.raw_token}

    def test_tracking_preset_connects_without_user_read(self):
        self.assertNotIn("user:read", self.token.scopes)

        response = self.client.get(
            "/api/v1/cinetrack/connection/",
            **self.headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertIs(body["authenticated"], True)
        self.assertTrue(body["account_id"])
        self.assertTrue(body["server_version"])
        self.assertEqual(
            body["api_extensions"],
            {
                "cinetrack_episode_events_v1": True,
                "cinetrack_bootstrap_v2": True,
                "episode_sql_pagination": True,
            },
        )

        preferences = self.client.get(
            "/api/v1/user/preferences/",
            **self.headers,
        )
        self.assertEqual(preferences.status_code, HTTP.FORBIDDEN)

    def test_probe_rejects_invalid_credentials(self):
        response = self.client.get(
            "/api/v1/cinetrack/connection/",
            HTTP_X_API_KEY="flp_invalid_connection_token",
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_probe_does_not_contact_metadata_provider(self):
        self._metadata_mock.reset_mock()
        response = self.client.get(
            "/api/v1/cinetrack/connection/",
            **self.headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self._metadata_mock.assert_not_called()

    def test_account_identity_is_stable_and_account_specific(self):
        first = self.client.get(
            "/api/v1/cinetrack/connection/",
            **self.headers,
        ).json()["account_id"]
        second = self.client.get(
            "/api/v1/cinetrack/connection/",
            **self.headers,
        ).json()["account_id"]
        self.assertEqual(first, second)

        _, other_raw = IntegrationToken.generate(
            user=self.user2,
            name="Other CineTrack",
        )
        other = self.client.get(
            "/api/v1/cinetrack/connection/",
            HTTP_X_API_KEY=other_raw,
        ).json()["account_id"]
        self.assertNotEqual(first, other)

    def test_tracking_preset_reaches_cinetrack_bootstrap_routes(self):
        movie = self.call_api(
            "post",
            "api_cinetrack_bootstrap_movies_ensure",
            payload={
                "movies": [
                    {
                        "source": "tmdb",
                        "media_id": "99501",
                        "title": "Scoped bootstrap movie",
                        "status": 0,
                    }
                ]
            },
            headers=self.headers,
        )
        self.assertEqual(movie.status_code, HTTP.OK)

        show = self.call_api(
            "post",
            "api_cinetrack_bootstrap_shows_ensure",
            payload={
                "shows": [
                    {
                        "source": "tmdb",
                        "media_id": "99502",
                        "title": "Scoped bootstrap show",
                        "status": 0,
                    }
                ]
            },
            headers=self.headers,
        )
        self.assertEqual(show.status_code, HTTP.OK)
