"""The web Statistics screen (v2 P4-H1).

GET /api/v1/statistics/screen/ reads the Statistics page's own context; these
tests hold its range, summaries, highlights and controls to the page's.
"""

import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks  # noqa: F401  - saving a Movie reaches events.tasks lazily
from app.models import Item, MediaTypes, Movie, Sources, Status


@patch("app.providers.services.get_media_metadata", side_effect=RuntimeError("no network"))
class StatisticsScreenTests(TestCase):
    """The screen follows the page."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "h1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        now = timezone.now()
        for index, title in enumerate(("Seed One", "Seed Two", "Seed Three")):
            item = Item.objects.create(
                media_id=f"h1-{index}",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=title,
                runtime_minutes=100,
            )
            watched = now - datetime.timedelta(days=3 + index * 10)
            Movie.objects.create(
                user=self.user,
                item=item,
                status=Status.COMPLETED.value,
                score=7 + index,
                start_date=watched - datetime.timedelta(hours=2),
                end_date=watched,
            )

    def _screen(self, query=""):
        response = self.client.get(reverse("api_statistics_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_all_time_follows_the_page(self, _metadata):
        query = "?start-date=all&end-date=all"
        page = self.client.get(reverse("statistics") + query)
        screen = self._screen(query)

        self.assertFalse(screen["database_error"])
        self.assertEqual(screen["range"]["name"], "All Time")
        self.assertFalse(screen["range"]["finite"])
        self.assertEqual(screen["compare"]["mode"], "none")
        page_all = page.context["summary_stats_by_type"]["all"]
        self.assertEqual(screen["summaries"]["all"]["completed"], page_all["completed"])
        self.assertEqual(screen["summaries"]["all"]["total"], page_all["total"])
        self.assertEqual(screen["summaries"]["movie"]["has_score"], True)
        self.assertEqual(screen["highlights"]["all"]["last_play"]["title"], "Seed One")
        self.assertTrue(screen["highlights"]["all"]["last_play"]["caption"].startswith("Played "))
        values = [option["value"] for option in screen["media_types"]]
        self.assertEqual(values[:4], ["all", "tv", "movie", "anime"])
        self.assertEqual(
            [preset["name"] for preset in screen["ranges"]][-1],
            "All Time",
        )
        self.assertEqual(screen["ranges"][-1]["dates"], "All activity")
        self.assertEqual(screen["urls"]["refresh"], reverse("refresh_statistics"))
        self.assertEqual(screen["rating_scale_max"], 10)

    def test_a_finite_range_offers_its_comparisons(self, _metadata):
        today = timezone.localdate()
        start = (today - datetime.timedelta(days=29)).isoformat()
        screen = self._screen(f"?start-date={start}&end-date={today.isoformat()}&compare=previous_period")

        self.assertTrue(screen["range"]["finite"])
        self.assertEqual(screen["range"]["name"], "Last 30 Days")
        self.assertEqual(screen["compare"]["mode"], "previous_period")
        options = {option["value"]: option for option in screen["compare"]["options"]}
        self.assertTrue(options["previous_period"]["dates"])
        self.assertTrue(options["last_year"]["dates"])
        self.assertEqual(options["none"]["dates"], "")
        self.assertEqual(screen["range"]["last_day"], today.isoformat())
        self.assertIn("state", screen["activity"])

    @patch("app.statistics_views.statistics_cache.get_statistics_data", side_effect=OperationalError("locked"))
    def test_a_database_error_is_an_error_state(self, _stats, _metadata):
        screen = self._screen("?start-date=all&end-date=all")

        self.assertTrue(screen["database_error"])
        self.assertEqual(screen["summaries"], {})
