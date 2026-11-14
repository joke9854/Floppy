from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from app.interactive_requests import should_mark_interactive_request


class PollingRequestsNotInteractiveTests(SimpleTestCase):
    """Background polls must not keep the user marked active."""

    def _htmx_get(self, path):
        return RequestFactory().get(path, HTTP_HX_REQUEST="true")

    def test_polling_endpoints_are_not_interactive(self):
        paths = [
            reverse("active_playback_fragment"),
            reverse("episode_history_poll", args=[7]),
            reverse(
                "trakt_series_graph_fragment",
                kwargs={"source": "tmdb", "media_id": "1668"},
            ),
        ]
        for path in paths:
            with self.subTest(path=path):
                self.assertFalse(should_mark_interactive_request(self._htmx_get(path)))

    def test_normal_htmx_page_request_is_interactive(self):
        self.assertTrue(should_mark_interactive_request(self._htmx_get("/medialist/movie")))
