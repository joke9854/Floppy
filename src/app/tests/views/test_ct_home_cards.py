import re
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import Episode, Item, MediaTypes, Season, Sources, Status
from app.templatetags.app_tags import tmdb_size, tmdb_srcset
from events.models import Event
from users.models import ThemeChoices

POSTER = "https://image.tmdb.org/t/p/w500/abc.jpg"


class TmdbImageSizeFilterTests(TestCase):
    """F5: rendered TMDB URLs change size; stored URLs and other hosts don't."""

    def test_tmdb_size_rewrites_only_the_size_segment(self):
        self.assertEqual(
            tmdb_size(POSTER, "w185"),
            "https://image.tmdb.org/t/p/w185/abc.jpg",
        )
        self.assertEqual(
            tmdb_size("https://image.tmdb.org/t/p/original/abc.jpg", "w342"),
            "https://image.tmdb.org/t/p/w342/abc.jpg",
        )

    def test_other_urls_pass_through(self):
        for value in ("http://example.com/w500/a.jpg", "", None):
            with self.subTest(value=value):
                self.assertEqual(tmdb_size(value, "w185"), value)
                self.assertEqual(tmdb_srcset(value), "")

    @override_settings(IMAGE_CACHE_ENABLED=False)
    def test_srcset_lists_each_width(self):
        self.assertEqual(
            tmdb_srcset(POSTER, "w185,w342"),
            "https://image.tmdb.org/t/p/w185/abc.jpg 185w, "
            "https://image.tmdb.org/t/p/w342/abc.jpg 342w",
        )


class CineTrackHomeCardTests(TestCase):
    """W2: Home rows use the CineTrack cards for the CineTrack theme only."""

    def setUp(self):
        self.credentials = {"username": "cards", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title="Friends",
            image=POSTER,
        )
        self.season = Season.objects.create(
            item=self.season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        for number in range(1, 9):
            Event.objects.create(
                item=self.season_item,
                content_number=number,
                datetime=timezone.now() - timezone.timedelta(days=30 - number),
            )
        for number in range(1, 5):
            episode_item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                season_number=1,
                episode_number=number,
                title="Friends",
                image=POSTER,
            )
            Episode.objects.create(
                item=episode_item,
                related_season=self.season,
                end_date=timezone.now() - timezone.timedelta(days=10 - number),
            )

    def _use_theme(self, theme):
        self.user.theme = theme
        self.user.save(update_fields=["theme"])

    def _hydrated_home(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        if response.context.get("defer_remaining_groups"):
            html += self.client.get(reverse("home_rest_fragment")).content.decode()
        return html

    def test_cinetrack_home_renders_progress_card_with_check_form(self):
        self._use_theme(ThemeChoices.CINETRACK)
        html = self._hydrated_home()

        self.assertIn('class="ct-progress-card"', html)
        self.assertIn("S1 E5", html)
        self.assertIn(f'hx-post="{reverse("episode_save")}?next={reverse("home")}"', html)
        self.assertIn('name="episode_number" value="5"', html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('decoding="async"', html)
        self.assertIn("https://image.tmdb.org/t/p/w185/abc.jpg 185w", html)
        self.assertNotIn('class="media-card ', html.split("ct-progress-card", 1)[1][:4000])

    def test_classic_theme_keeps_the_classic_card(self):
        self._use_theme(ThemeChoices.DARK)
        html = self._hydrated_home()

        self.assertNotIn("ct-progress-card", html)
        self.assertNotIn("ct-poster-card", html)
        self.assertIn('class="home-row-card w-44 shrink-0"', html)

    def test_load_more_rows_use_the_same_cards(self):
        self._use_theme(ThemeChoices.CINETRACK)
        response = self.client.get(reverse("home"))
        row_id = next(
            row["row_id"]
            for group in response.context["home_groups"]
            for row in group["rows"]
        )
        response = self.client.get(
            reverse("home"),
            {"load_row": row_id, "offset": 0},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertTrue("ct-progress-card" in html or "ct-poster-card" in html)
        self.assertNotIn('class="media-card ', html)

    def test_check_records_the_exact_click_time(self):
        """The check's fields, posted with the browser's local time, keep it to the second."""
        self._use_theme(ThemeChoices.CINETRACK)
        html = self._hydrated_home()
        form = re.search(r'<form class="ct-check-form".*?</form>', html, re.DOTALL).group(0)
        fields = dict(re.findall(r'name="(\w+)" value="([^"]*)"', form))
        fields["end_date"] = "2026-10-26T21:14:37"

        with (
            patch("app.save_views.resolve_episode_coordinate"),
            patch(
                "app.save_views.fork_services_episode.resolve_or_create_season",
                return_value=self.season,
            ),
            patch(
                "app.models.providers.services.get_media_metadata",
                return_value={
                    "max_progress": 8,
                    "season/1": {
                        "details": {"episodes": 8},
                        "episodes": [{"episode_number": n} for n in range(1, 9)],
                    },
                },
            ),
        ):
            response = self.client.post(
                f"{reverse('episode_save')}?next={reverse('home')}",
                fields,
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(response.status_code, 200)
        watched = Episode.objects.get(
            related_season=self.season,
            item__episode_number=5,
        )
        expected = timezone.make_aware(datetime(2026, 10, 26, 21, 14, 37))
        self.assertEqual(watched.end_date, expected)
        self.assertEqual(str(watched.watch_operation_id), fields["watch_operation_id"])
