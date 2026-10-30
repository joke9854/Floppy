from datetime import datetime
from unittest.mock import patch

from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import Item, MediaTypes, Movie, Sources, Status
from users.models import ThemeChoices


class StatisticsRecapTests(TestCase):
    """A7: the monthly recap card."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="recap-user",
            password="12345",
        )
        self.client.force_login(self.user)
        self.month_start = timezone.localdate().replace(day=1)
        played_at = timezone.make_aware(
            datetime.combine(self.month_start, datetime.min.time()),
            timezone.get_current_timezone(),
        )
        item = Item.objects.create(
            media_id="recap-1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Recap Movie",
            image="http://example.com/recap.jpg",
            runtime_minutes=125,
        )
        Movie.objects.create(
            user=self.user,
            item=item,
            status=Status.COMPLETED.value,
            progress=1,
            start_date=played_at,
            end_date=played_at,
        )

    def test_current_month_lists_time_plays_and_top_movie(self):
        response = self.client.get(reverse("statistics_recap"))

        self.assertEqual(response.status_code, 200)
        recap = response.context["recap"]
        self.assertEqual(recap["month"], self.month_start.strftime("%Y-%m"))
        self.assertEqual(recap["total_time"], "2h 5min")
        self.assertEqual(
            [(play["media_type"], play["count"]) for play in recap["plays"]],
            [(MediaTypes.MOVIE.value, 1)],
        )
        self.assertEqual(recap["plays"][0]["label"], "Movies")
        self.assertEqual(recap["top"][0]["label"], "Movies")
        self.assertEqual(recap["top"][0]["entries"][0]["title"], "Recap Movie")
        self.assertContains(response, 'id="ct-recap-data"')
        self.assertContains(response, "data-recap-save")
        self.assertIsNone(response.context["next_month"])

    def test_previous_month_is_empty_and_links_forward(self):
        previous = self.month_start - relativedelta(months=1)

        response = self.client.get(
            reverse("statistics_recap"),
            {"month": previous.strftime("%Y-%m")},
        )

        recap = response.context["recap"]
        self.assertEqual(recap["plays"], [])
        self.assertEqual(recap["top"], [])
        self.assertContains(response, "Nothing tracked this month yet.")
        self.assertEqual(
            response.context["next_month"],
            self.month_start.strftime("%Y-%m"),
        )

    def test_future_or_invalid_month_falls_back_to_current(self):
        future = self.month_start + relativedelta(months=2)

        for month in (future.strftime("%Y-%m"), "nonsense"):
            response = self.client.get(reverse("statistics_recap"), {"month": month})
            self.assertEqual(
                response.context["recap"]["month"],
                self.month_start.strftime("%Y-%m"),
            )

    def test_month_still_building_says_so_instead_of_empty(self):
        previous = self.month_start - relativedelta(months=1)

        with patch(
            "app.statistics_views.statistics_cache._has_missing_day_caches",
            return_value=True,
        ):
            response = self.client.get(
                reverse("statistics_recap"),
                {"month": previous.strftime("%Y-%m")},
            )

        self.assertTrue(response.context["counting"])
        self.assertContains(response, "Still counting this month.")
        self.assertNotContains(response, "Nothing tracked this month yet.")

    def test_statistics_links_to_recap_only_in_cinetrack(self):
        recap_url = reverse("statistics_recap")

        response = self.client.get(reverse("statistics"))
        self.assertNotContains(response, f'href="{recap_url}"')

        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        response = self.client.get(reverse("statistics"))
        self.assertContains(response, f'href="{recap_url}"')
