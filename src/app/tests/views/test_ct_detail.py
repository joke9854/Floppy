from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import MediaTypes, Sources
from app.templatetags.app_tags import ct_detail_backdrop, ct_series_progress
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

        self.assertContains(response, 'class="ct-detail-hero"')
        self.assertContains(response, "https://image.tmdb.org/t/p/w1280/back.jpg 1280w")
        self.assertContains(response, 'src="https://image.tmdb.org/t/p/w92/poster.jpg"')
        self.assertContains(response, 'id="detail-carousel-wrap"', count=1)
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
