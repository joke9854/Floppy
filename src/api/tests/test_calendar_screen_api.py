"""The web Calendar screen (v2 P4-F).

GET /api/v1/calendar/screen/ reads the Calendar page's own context; these
tests hold its month and releases to the page's.
"""

import datetime

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import Item, MediaTypes, Movie, Sources, Status
from events.models import Event

JSON = {"HTTP_ACCEPT": "application/json"}


class CalendarScreenTests(TestCase):
    """The screen follows the page's month and rows."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "f1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=self.item, user=self.user, status=Status.PLANNING.value)
        today = timezone.localdate()
        self.when = timezone.make_aware(datetime.datetime(today.year, today.month, 15, 21, 0))
        self.event = Event.objects.create(item=self.item, datetime=self.when)

    def _screen(self, query=""):
        response = self.client.get(reverse("api_calendar_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_the_month_follows_the_page(self):
        page = self.client.get(reverse("calendar"))
        screen = self._screen()

        today = timezone.localdate()
        self.assertEqual((screen["year"], screen["month"]), (today.year, today.month))
        self.assertEqual(screen["weeks"], page.context["calendar"])
        self.assertEqual(screen["weekdays"], page.context["weekday_headers"])
        self.assertEqual([d["day"] for d in screen["days"]], sorted(page.context["release_dict"]))
        release = screen["days"][0]["releases"][0]
        self.assertEqual(release["title"], "The Matrix")
        self.assertEqual(release["status"], Status.PLANNING.value)
        self.assertEqual(release["type_label"], "Movie")
        self.assertTrue(release["time"].startswith("at "))
        self.assertTrue(release["href"].startswith("/details/tmdb/movie/603/"))
        movie = next(t for t in screen["filter_types"] if t["value"] == "movie")
        self.assertTrue(movie["in_month"])
        self.assertEqual(movie["month_statuses"], [Status.PLANNING.value])
        self.assertIn(str(self.user.calendar_token), screen["export"]["url"])

    def test_navigation_and_view_save_the_layout(self):
        screen = self._screen("?month=1&year=2030&view=list")

        self.assertEqual((screen["year"], screen["month"]), (2030, 1))
        self.assertEqual(screen["prev"], {"year": 2029, "month": 12})
        self.assertEqual(screen["view"], "list")
        self.assertEqual(screen["days"], [])
        self.user.refresh_from_db()
        self.assertEqual(self.user.calendar_layout, "list")

    def test_fetch_new_releases_answers_json(self):
        from unittest.mock import patch

        with patch("events.views.tasks.reload_calendar.delay") as delay:
            queued = self.client.post(reverse("reload_calendar"), **JSON)

        self.assertEqual(
            queued.json()["message"], "The task to refresh upcoming releases has been queued."
        )
        delay.assert_called_once_with(user_id=self.user.id)

    def test_integration_tokens_cannot_call_it(self):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(user=self.user, name="cal", scopes=["catalog:read"])
        response = Client().get(reverse("api_calendar_screen"), HTTP_X_API_KEY=raw)

        self.assertEqual(response.status_code, 403)
