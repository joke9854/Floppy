from http import HTTPStatus as HTTP  # noqa: N814

from django.urls import reverse

from app import home_sections
from app.models import Status
from app.tests.test_home_sections import InProgressFixtures
from integrations.models import IntegrationToken


class ContinueWatchingApiTests(InProgressFixtures):
    """GET /api/v1/continue-watching/: the In Progress row as a list."""

    url = reverse("api_continue_watching")

    def _token(self, scopes):
        _, raw = IntegrationToken.generate(
            user=self.user, name="continue watching test", scopes=scopes
        )
        return raw

    def test_requires_a_credential(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_a_rejected_bearer_token_is_unauthorized(self):
        response = self.client.get(
            self.url, HTTP_AUTHORIZATION="Bearer flp_not_a_real_token"
        )

        self.assertEqual(response.status_code, HTTP.UNAUTHORIZED)

    def test_requires_the_progress_read_scope(self):
        raw = self._token(["catalog:read"])

        response = self.client.get(self.url, HTTP_X_API_KEY=raw)

        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_progress_read_reads_the_list(self):
        raw = self._token(["progress:read"])

        response = self.client.get(self.url, HTTP_X_API_KEY=raw)

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json(), {"results": []})

    def test_entries_match_the_home_row_in_order(self):
        self._movie("630", Status.IN_PROGRESS.value, position=1800, duration=7200)
        self._show(
            "1",
            Status.IN_PROGRESS.value,
            released=4,
            watched=[1],
            part_watched=2,
            part_position=1200,
            part_duration=2700,
        )
        self._show("2", Status.IN_PROGRESS.value, released=3, watched=[1])
        raw = self._token(["progress:read", "catalog:read"])

        results = self.client.get(self.url, HTTP_X_API_KEY=raw).json()["results"]
        home = self.client.get(reverse("api_home"), HTTP_X_API_KEY=raw).json()
        home_group = next(
            group for group in home["groups"] if group["media_type"] == "in_progress"
        )

        self.assertEqual(
            [entry["item"]["title"] for entry in results],
            [item["item"]["title"] for item in home_group["rows"][0]["items"]],
        )
        self.assertEqual(
            [entry["item"]["title"] for entry in results],
            [entry.item.title for entry in home_sections.build_continue_watching(self.user)],
        )

    def test_entry_fields_carry_the_target_and_times(self):
        self._show(
            "1",
            Status.IN_PROGRESS.value,
            released=4,
            watched=[1],
            part_watched=2,
            part_position=1200,
            part_duration=2700,
        )
        self._movie("631", Status.COMPLETED.value, position=1800, duration=7200)
        raw = self._token(["progress:read"])

        results = {
            entry["item"]["title"]: entry
            for entry in self.client.get(self.url, HTTP_X_API_KEY=raw).json()["results"]
        }

        show = results["Show 1"]
        self.assertEqual(show["kind"], "show")
        self.assertEqual(show["target"]["season_number"], 1)
        self.assertEqual(show["target"]["episode_number"], 2)
        self.assertEqual(show["target"]["title"], "Show 1")
        self.assertIsNotNone(show["target"]["item_id"])
        self.assertEqual(show["position_seconds"], 1200)
        self.assertEqual(show["duration_seconds"], 2700)
        self.assertEqual(show["remaining_seconds"], 1500)
        self.assertEqual(show["progress_percent"], 44)
        self.assertEqual((show["watched_count"], show["released_count"]), (1, 4))
        self.assertFalse(show["is_rewatch"])
        self.assertIsNotNone(show["last_activity"])

        movie = results["Movie 631"]
        self.assertEqual(movie["kind"], "movie")
        self.assertIsNone(movie["target"])
        self.assertEqual(movie["remaining_seconds"], 5400)
        self.assertTrue(movie["is_rewatch"])
