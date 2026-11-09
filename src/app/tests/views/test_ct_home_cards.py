import json
import re
from datetime import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.home_sections import HomeRowEntry
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
        # Home sections and backdrop lock keys are cached per user id, and ids repeat across tests.
        cache.clear()
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
        return response.content.decode()

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

    def test_progress_card_opens_the_next_episode(self):
        self._use_theme(ThemeChoices.CINETRACK)
        html = self._hydrated_home()

        card = html.split('class="ct-progress-card"', 1)[1][:6000]
        episode_url = reverse(
            "episode_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_id": "1668",
                "title": "friends",
                "season_number": 1,
                "episode_number": 5,
            },
        )
        self.assertIn(f'href="{episode_url}" class="ct-progress-media"', card)
        self.assertIn(f'href="{episode_url}" class="ct-progress-title"', card)

    def test_progress_card_uses_a_cached_backdrop_without_fetching(self):
        self._use_theme(ThemeChoices.CINETRACK)
        cache.set(
            "tmdb_backdrop_tv_1668",
            "https://image.tmdb.org/t/p/w1280/backdrop.jpg",
        )
        with patch("app.backdrops.resolve_backdrop") as resolve:
            html = self._hydrated_home()

        resolve.assert_not_called()
        card = html.split('class="ct-progress-card"', 1)[1][:3000]
        self.assertIn("/w780/backdrop.jpg", card)
        self.assertNotIn("is-poster", card)

    def test_progress_card_falls_back_to_the_poster(self):
        self._use_theme(ThemeChoices.CINETRACK)
        html = self._hydrated_home()

        card = html.split('class="ct-progress-card"', 1)[1][:3000]
        self.assertIn("ct-progress-art is-poster", card)

    def test_progress_card_miss_queues_one_backdrop_fetch(self):
        self._use_theme(ThemeChoices.CINETRACK)
        with (
            patch("app.tasks.fetch_backdrop.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self._hydrated_home()
            self._hydrated_home()

        delay.assert_called_once()
        self.assertEqual(delay.call_args.args[0]["media_id"], "1668")

    def test_in_progress_show_without_a_next_episode_keeps_the_landscape_card(self):
        self._use_theme(ThemeChoices.CINETRACK)
        request = RequestFactory().get(reverse("home"))
        request.user = self.user
        entry = HomeRowEntry(
            item=self.season_item,
            media=self.season,
            show_progress_controls=False,
        )

        html = render_to_string(
            "app/components/ct/home_grid.html",
            {"media_list": {"items": [entry]}},
            request=request,
        )

        self.assertIn('class="ct-progress-card"', html)
        self.assertNotIn("data-ct-check", html)
        self.assertNotIn("ct-poster-card", html)

    def test_cinetrack_home_has_the_v2_header_and_row_heading(self):
        self._use_theme(ThemeChoices.CINETRACK)
        html = self._hydrated_home()

        self.assertIn('class="ct-page-title"', html)
        self.assertIn(f'href="{reverse("notifications")}"', html)
        self.assertIn('class="ct-row-head"', html)
        self.assertIn('class="ct-row-link"', html)
        self.assertNotIn('aria-label="Scroll right"', html)

    def _check_fields(self):
        html = self._hydrated_home()
        form = re.search(r'<form class="ct-check-form".*?</form>', html, re.DOTALL).group(0)
        return dict(re.findall(r'name="(\w+)" value="([^"]*)"', form))

    def _post_check(self, fields):
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
        return response

    def test_check_records_the_exact_click_time(self):
        """The check's fields, posted with the browser's local time, keep it to the second."""
        self._use_theme(ThemeChoices.CINETRACK)
        fields = self._check_fields()
        fields["end_date"] = "2026-10-26T21:14:37"

        self._post_check(fields)

        watched = Episode.objects.get(
            related_season=self.season,
            item__episode_number=5,
        )
        expected = timezone.make_aware(datetime(2026, 10, 26, 21, 14, 37))
        self.assertEqual(watched.end_date, expected)
        self.assertEqual(str(watched.watch_operation_id), fields["watch_operation_id"])

    def test_check_toast_offers_undo_of_the_new_play(self):
        """M5: the toast names the play it added, and undoing it deletes only that play."""
        self._use_theme(ThemeChoices.CINETRACK)
        fields = self._check_fields()
        fields["end_date"] = "2026-10-26T21:14:37"

        response = self._post_check(fields)

        undo = json.loads(response["HX-Trigger"])["showToast"]["undo"]
        watched = Episode.objects.get(related_season=self.season, item__episode_number=5)
        self.assertEqual(
            undo,
            {"url": reverse("media_delete"), "instanceId": watched.id, "mediaType": "episode"},
        )
        before = Episode.objects.filter(related_season=self.season).count()
        with patch("app.save_views._write_episode_save_oob"):
            self.client.post(
                f"{undo['url']}?next={reverse('home')}",
                {"instance_id": undo["instanceId"], "media_type": undo["mediaType"]},
                HTTP_HX_REQUEST="true",
            )
        self.assertFalse(Episode.objects.filter(id=watched.id).exists())
        self.assertEqual(Episode.objects.filter(related_season=self.season).count(), before - 1)
