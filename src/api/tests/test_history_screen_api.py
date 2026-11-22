"""The web History screen (v2 P4-E).

GET /api/v1/history/screen/ reads the History page's own context; these
tests hold its days and rows to the page's.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import Item, MediaTypes, Movie, Sources, Status
from app.tests.views.test_history import _start_model_metadata_patches

JSON = {"HTTP_ACCEPT": "application/json"}


class HistoryScreenTests(TestCase):
    """The screen follows the page for the month view and filtered pages."""

    def setUp(self):
        cache.clear()
        _start_model_metadata_patches(self)
        self.credentials = {"username": "e1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        self.movie = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            score=8,
            end_date=timezone.now(),
        )

    def _screen(self, query=""):
        response = self.client.get(reverse("api_history_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_a_filtered_page_follows_the_page(self):
        query = f"?media_type=movie&media_id={self.item.media_id}&source={self.item.source}"
        page = self.client.get(reverse("history") + query)
        screen = self._screen(query)

        self.assertIsNone(screen["month"])
        self.assertEqual(screen["mode"], "activity")
        self.assertEqual(
            [day["date"] for day in screen["days"]],
            [str(day.get("date_display") or day.get("date")) for day in page.context["history_days"]],
        )
        row = screen["days"][0]["entries"][0]
        self.assertEqual(row["title"], "Test Movie")
        self.assertEqual(row["subtitle"], "Movie")
        self.assertEqual(row["score"], "8")
        self.assertEqual(row["item_id"], self.item.id)
        self.assertTrue(row["href"].startswith("/details/tmdb/movie/238/"))
        self.assertEqual(
            row["track"],
            {
                "media_type": "movie",
                "source": "tmdb",
                "media_id": "238",
                "season_number": None,
                "episode_number": None,
                "instance_id": self.movie.id,
            },
        )
        self.assertEqual(row["history_query"], "media_type=movie&media_id=238&source=tmdb")
        self.assertEqual(screen["filters"]["media_id"], "238")

    def test_the_month_view_has_its_navigation(self):
        screen = self._screen()

        month = screen["month"]
        now = timezone.localtime()
        self.assertEqual((month["year"], month["month"]), (now.year, now.month))
        self.assertIsNone(month["current"])
        self.assertIsNone(month["newer"])
        self.assertTrue(month["older"]["query"].startswith("year="))
        self.assertEqual(month["year_back"]["label"], str(now.year - 1))
        self.assertIn("movie", [t["value"] for t in screen["types"]])

    def test_release_mode_has_no_row_actions(self):
        screen = self._screen("?history_mode=release&media_type=movie")

        self.assertEqual(screen["mode"], "release")
        for day in screen["days"]:
            for row in day["entries"]:
                self.assertIsNone(row["track"])
                self.assertEqual(row["time"], "Released")

    def test_integration_tokens_cannot_call_it(self):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(user=self.user, name="history", scopes=["progress:read"])
        response = Client().get(reverse("api_history_screen"), HTTP_X_API_KEY=raw)

        self.assertEqual(response.status_code, 403)
