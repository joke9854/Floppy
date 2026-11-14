"""FORK: API errors are JSON with a code, never an HTML page or exception text."""

from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

import requests
from rest_framework.settings import api_settings

from api.exceptions import api_exception_handler
from app.providers import services

from .base import FloppyApiTestCase

SECRET = "internal-detail-that-must-not-leak"


def _provider_error(status_code=None):
    """A provider failure: a timeout when status_code is None, else an HTTP error."""
    if status_code is None:
        return services.ProviderAPIError("tmdb", requests.exceptions.ReadTimeout(SECRET))
    return services.ProviderAPIError("tmdb", SimpleNamespace(response=SimpleNamespace(status_code=status_code)))


class ExceptionHandlerTests(FloppyApiTestCase):
    """The DRF exception handler answers anything a view lets escape."""

    def test_handler_is_configured(self):
        self.assertIs(api_settings.EXCEPTION_HANDLER, api_exception_handler)

    def test_unexpected_error_is_json_500_without_text(self):
        with self.assertLogs("api.exceptions", level="ERROR"):
            response = api_exception_handler(RuntimeError(SECRET), {"view": None})
        self.assertEqual(response.status_code, HTTP.INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data, {"detail": "Internal server error.", "code": "server_error"})

    def test_provider_outage_is_503(self):
        response = api_exception_handler(_provider_error(), {"view": None})
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["code"], "provider_unavailable")
        self.assertEqual(response["Retry-After"], "30")

    def test_provider_not_found_is_404(self):
        response = api_exception_handler(_provider_error(404), {"view": None})
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
        self.assertEqual(response.data["code"], "not_found")

    def test_escaped_error_from_a_view_is_json(self):
        """A view that does not catch an error answers a typed JSON 500."""
        with (
            patch("api.views.services.search", side_effect=RuntimeError(SECRET)),
            self.assertLogs("api", level="ERROR"),
        ):
            response = self.call_api("get", "api_search_provider", args=("movie",), headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.INTERNAL_SERVER_ERROR)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["code"], "server_error")
        self.assertNotIn(SECRET, response.content.decode())


class ProviderOutageTests(FloppyApiTestCase):
    """Routes that ask a metadata provider answer 503 when it is down."""

    def assert_unavailable(self, response):
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")
        self.assertEqual(response["Retry-After"], "30")
        self.assertNotIn(SECRET, response.content.decode())

    def test_media_detail(self):
        with patch("api.views.services.get_media_metadata", side_effect=_provider_error()):
            response = self.call_api("get", "api_media_detail", args=("movie", "tmdb", "424242"), headers=self.auth_headers)
        self.assert_unavailable(response)

    def test_media_detail_keeps_404(self):
        with patch("api.views.services.get_media_metadata", side_effect=_provider_error(404)):
            response = self.call_api("get", "api_media_detail", args=("movie", "tmdb", "424242"), headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)

    def test_search(self):
        with patch("api.views.services.search", side_effect=_provider_error()), self.assertLogs("api", level="ERROR"):
            response = self.call_api("get", "api_search_provider", args=("movie",), headers=self.auth_headers)
        self.assert_unavailable(response)

    def test_playback_progress(self):
        with (
            patch("api.fork_views_playback.resolve_video_item", side_effect=_provider_error()),
            self.assertLogs("api", level="ERROR"),
        ):
            response = self.call_api(
                "put",
                "api_playback_progress",
                payload={"media_type": "movie", "ids": {"tmdb": "424242"}, "position_seconds": 120},
                headers=self.auth_headers,
            )
        self.assert_unavailable(response)

    def test_music_artist_by_musicbrainz_id(self):
        with (
            patch("app.fork_services_music.get_or_create_artist_from_musicbrainz", side_effect=_provider_error()),
            self.assertLogs("api", level="ERROR"),
        ):
            response = self.call_api(
                "post",
                "api_music_artists",
                payload={"musicbrainz_id": "11111111-1111-1111-1111-111111111111"},
                headers=self.auth_headers,
            )
        self.assert_unavailable(response)


class NoExceptionTextTests(FloppyApiTestCase):
    """Errors that are not provider outages never echo exception text."""

    def test_playback_progress_bug_is_500(self):
        with (
            patch("api.fork_views_playback.resolve_video_item", side_effect=RuntimeError(SECRET)),
            self.assertLogs("api", level="ERROR"),
        ):
            response = self.call_api(
                "put",
                "api_playback_progress",
                payload={"media_type": "movie", "ids": {"tmdb": "424242"}, "position_seconds": 120},
                headers=self.auth_headers,
            )
        self.assertEqual(response.status_code, HTTP.INTERNAL_SERVER_ERROR)
        self.assertEqual(response.json()["code"], "server_error")
        self.assertNotIn(SECRET, response.content.decode())

    @patch("apprise.Apprise")
    def test_notification_failure_hides_the_error(self, mock_apprise):
        self.user1.notification_urls = "json://localhost/webhook"
        self.user1.save(update_fields=["notification_urls"])
        mock_apprise.return_value.notify.side_effect = RuntimeError(SECRET)
        with self.assertLogs("api", level="ERROR"):
            response = self.call_api("post", "api_user_notification_test", payload={}, headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.BAD_GATEWAY)
        self.assertNotIn(SECRET, response.content.decode())
