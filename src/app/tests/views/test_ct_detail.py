from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from app.models import MediaTypes, Sources
from app.providers import tmdb
from app.templatetags.app_tags import (
    ct_detail_backdrop,
    ct_detail_next_episode,
    ct_season_covers,
    ct_series_progress,
    ct_v2_detail_type,
)
from users.models import ThemeChoices

BACKDROP = "https://image.tmdb.org/t/p/w1280/back.jpg"


def _watch(dropped=False):
    return SimpleNamespace(dropped=dropped)


class CineTrackSeriesProgressTests(TestCase):
    """W3: the series progress card's numbers and dashes."""

    def test_untracked_media_has_no_card(self):
        self.assertIsNone(ct_series_progress({"media_type": "tv"}, None))

    def test_season_counts_its_episodes(self):
        media = {
            "media_type": MediaTypes.SEASON.value,
            "max_progress": 4,
            "episodes": [
                {"episode_number": 1, "history": [_watch()]},
                {"episode_number": 2, "history": [_watch(dropped=True)]},
                {"episode_number": 3, "history": []},
                {"episode_number": 4},
            ],
        }
        progress = ct_series_progress(media, SimpleNamespace(completed_episode_count=1))

        self.assertEqual((progress["watched"], progress["total"], progress["percent"]), (1, 4, 25))
        self.assertEqual([dash["percent"] for dash in progress["dashes"]], [100, 0, 0, 0])
        self.assertEqual(progress["dashes"][0]["label"], "E1")

    def test_show_has_one_dash_per_season_without_specials(self):
        def season(number, episodes, watched):
            return {
                "item": {"season_number": number, "episode_count": episodes},
                "media": SimpleNamespace(completed_episode_count=watched) if watched is not None else None,
                "card_title": f"Season {number}" if number else "Specials",
            }

        media = {
            "media_type": MediaTypes.TV.value,
            "max_progress": 18,
            "related": {"seasons": [season(0, 3, 3), season(1, 8, 8), season(2, 10, 2), season(3, 0, None)]},
        }
        progress = ct_series_progress(media, SimpleNamespace(completed_episode_count=10))

        self.assertEqual(progress["percent"], 56)
        self.assertEqual(
            [(dash["label"], dash["percent"]) for dash in progress["dashes"]],
            [("Season 1", 100), ("Season 2", 20), ("Season 3", 0)],
        )


class CineTrackDetailBackdropTests(TestCase):
    """W3: seasons and episodes resolve their show's cached backdrop."""

    def setUp(self):
        cache.clear()

    def test_season_uses_the_show_backdrop(self):
        cache.set("tmdb_backdrop_tv_1399", BACKDROP)
        media = {"source": Sources.TMDB.value, "media_type": MediaTypes.SEASON.value, "media_id": "1399"}

        self.assertEqual(ct_detail_backdrop(media), BACKDROP)

    def test_incomplete_identity_has_none(self):
        self.assertIsNone(ct_detail_backdrop({"source": Sources.TMDB.value}))


@override_settings(IMAGE_CACHE_ENABLED=False)
class CineTrackDetailPageTests(TestCase):
    """W3: the CineTrack hero replaces the top section for that theme only."""

    def setUp(self):
        cache.clear()
        cache.set("tmdb_backdrop_movie_238", BACKDROP)
        self.credentials = {"username": "detail", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.url = reverse(
            "media_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "238",
                "title": "test-movie",
            },
        )

    def _get(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "overview": "Test overview",
            "release_date": "2023-01-01",
        }
        return self.client.get(self.url)

    @patch("app.providers.services.get_media_metadata")
    def test_cinetrack_renders_backdrop_hero_and_keeps_carousel_target(self, mock_get_metadata):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])

        response = self._get(mock_get_metadata)

        self.assertContains(response, 'class="ct-detail-hero ct-detail-hero--v2"')
        self.assertContains(response, "https://image.tmdb.org/t/p/w1280/back.jpg 1280w")
        self.assertContains(response, 'src="https://image.tmdb.org/t/p/w92/poster.jpg"')
        # v2 moves the trailer and photos below the hero, into the sections.
        self.assertNotContains(response, 'id="detail-carousel-wrap"')
        self.assertContains(response, 'id="detail-secondary-content"', count=1)
        self.assertContains(response, "data-poster-accent-scope")
        self.assertNotContains(response, "detail-carousel-grid")

    @patch("app.providers.services.get_media_metadata")
    def test_classic_theme_keeps_the_classic_top_section(self, mock_get_metadata):
        response = self._get(mock_get_metadata)

        self.assertContains(response, "detail-carousel-grid")
        self.assertNotContains(response, "ct-detail-hero")
        self.assertNotContains(response, "ct-detail-backdrop")

    @patch("app.providers.services.get_media_metadata")
    def test_cinetrack_detail_has_keyboard_shortcut_hooks(self, mock_get_metadata):
        """A5: the shortcut list and the S target render in the CineTrack shell only."""
        classic = self._get(mock_get_metadata)
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        cinetrack = self._get(mock_get_metadata)

        self.assertNotContains(classic, "data-ct-shortcuts")
        self.assertContains(cinetrack, "data-ct-shortcuts")
        self.assertContains(cinetrack, 'data-ct-shortcut="track"')
        self.assertContains(cinetrack, 'data-episode-save-url="/episode_save"')

    @patch("app.providers.services.get_media_metadata")
    def test_cinetrack_sections_fragment_is_one_column_with_the_carousel(self, mock_get_metadata):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "details": {"status": "Released", "certification": "R"},
            "cast": [{"person_id": "1", "name": "Al Pacino", "role": "Michael Corleone"}],
        }

        response = self.client.get(f"{self.url}?fragment=secondary")

        self.assertContains(response, 'class="ct-detail-sections"')
        self.assertContains(response, 'id="detail-carousel-wrap"', count=1)
        self.assertContains(response, "Information")
        self.assertContains(response, "Michael Corleone")
        self.assertNotContains(response, "md:w-1/4 md:max-w-[250px]")

    @patch("app.providers.services.get_media_metadata")
    def test_cinetrack_hero_lists_where_to_watch(self, mock_get_metadata):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.watch_provider_region = "US"
        self.user.save(update_fields=["theme", "watch_provider_region"])
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "providers": {
                "US": {
                    "link": "https://www.themoviedb.org/movie/238/watch?locale=US",
                    "flatrate": [{"provider_id": 8, "provider_name": "Netflix", "logo_path": "/n.png"}],
                    "rent": [{"provider_id": 2, "provider_name": "Apple TV Store", "logo_path": "/a.png"}],
                    "buy": [{"provider_id": 2, "provider_name": "Apple TV Store", "logo_path": "/a.png"}],
                },
            },
        }

        response = self.client.get(self.url)

        self.assertContains(response, 'class="ct-watch-on"')
        self.assertContains(response, "Netflix")
        self.assertContains(response, "Rent · Buy")
        self.assertContains(response, "via JustWatch")


class CineTrackWatchOnTests(TestCase):
    """v2: the "Watch on" row keeps rent/buy, after subscription."""

    def test_subscription_then_rent_buy_with_one_chip_per_provider(self):
        providers = {
            "IT": {
                "link": "https://tmdb/watch",
                "flatrate": [
                    {"provider_id": 2, "provider_name": "B", "display_priority": 5},
                    {"provider_id": 1, "provider_name": "A", "display_priority": 1},
                ],
                "free": [{"provider_id": 3, "provider_name": "C", "display_priority": 9}],
                "rent": [
                    {"provider_id": 1, "provider_name": "A", "display_priority": 1},
                    {"provider_id": 4, "provider_name": "D", "display_priority": 3},
                ],
                "buy": [{"provider_id": 4, "provider_name": "D", "display_priority": 3}],
            },
        }

        row = tmdb.watch_on_providers(providers, "IT")

        self.assertEqual([p["provider_name"] for p in row["subscription"]], ["A", "B", "C"])
        self.assertEqual(
            [(p["provider_name"], p["offers"]) for p in row["rent_buy"]],
            [("D", ["rent", "buy"])],
        )
        self.assertEqual(row["link"], "https://tmdb/watch")

    def test_no_row_without_a_region_or_providers(self):
        self.assertIsNone(tmdb.watch_on_providers({"IT": {"flatrate": []}}, "IT"))
        self.assertIsNone(tmdb.watch_on_providers({"IT": {"rent": [{"provider_id": 1}]}}, "UNSET"))
        self.assertIsNone(tmdb.watch_on_providers(None, "IT"))


class CineTrackDetailTagTests(TestCase):
    """v2: season covers, the up-next episode and the v2 media types."""

    def test_season_covers_put_specials_last_and_default_to_the_first_season(self):
        show = {
            "related": {
                "seasons": [
                    {"item": {"season_number": 0, "image": "s0.jpg"}},
                    {"item": {"season_number": 2, "season_title": "Part Two"}},
                    {"season_number": 1, "season_title": "Season 1"},
                ],
            },
        }

        covers = ct_season_covers(show)

        self.assertEqual(
            [(c["number"], c["label"], c["short"]) for c in covers],
            [(1, "Season 1", "S1"), (2, "Part Two", "S2"), (0, "Specials", "Specials")],
        )
        self.assertEqual([c["current"] for c in covers], [True, False, False])
        self.assertTrue(ct_season_covers(show, 2)[1]["current"])

    def test_season_next_episode_is_the_first_aired_one_without_a_watch(self):
        past = timezone.now() - timedelta(days=3)
        future = timezone.now() + timedelta(days=3)
        media = {
            "media_type": MediaTypes.SEASON.value,
            "media_id": "1",
            "source": Sources.TMDB.value,
            "season_number": 2,
            "episodes": [
                {"episode_number": 1, "air_date": past, "history": [_watch()]},
                {"episode_number": 2, "air_date": None, "history": []},
                {"episode_number": 3, "air_date": past, "history": []},
                {"episode_number": 4, "air_date": future, "history": []},
            ],
        }

        self.assertEqual(ct_detail_next_episode(media, None)["episode_number"], 3)
        media["episodes"][2]["air_date"] = future
        self.assertIsNone(ct_detail_next_episode(media, None))

    def test_v2_covers_video_types_only(self):
        self.assertTrue(ct_v2_detail_type(MediaTypes.SEASON.value))
        self.assertTrue(ct_v2_detail_type(MediaTypes.MOVIE.value))
        self.assertFalse(ct_v2_detail_type(MediaTypes.BOOK.value))
