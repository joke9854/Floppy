from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import MediaTypes, Sources
from app.providers import fanart
from app.providers.services import ProviderAPIError
from users.models import ThemeChoices

LOGO = "https://assets.fanart.tv/fanart/movies/238/hdmovielogo/the-logo.png"
POSTER = "https://assets.fanart.tv/fanart/movies/238/movieposter/the-poster.jpg"
BACKGROUND = "https://assets.fanart.tv/fanart/movies/238/moviebackground/the-bg.jpg"
MOVIE = {"source": Sources.TMDB.value, "media_type": MediaTypes.MOVIE.value, "media_id": "238"}


def _not_found():
    response = requests.Response()
    response.status_code = 404
    return ProviderAPIError("fanart", requests.exceptions.HTTPError(response=response))


@override_settings(FANART_API_KEY="test-key", TMDB_LANG="en")
class FanartArtworkTests(TestCase):
    """fanart.tv lookups: which id, which image, and what is cached."""

    def setUp(self):
        cache.clear()

    @override_settings(FANART_API_KEY="")
    def test_without_a_key_there_is_no_art_and_no_request(self):
        with patch("app.providers.services.api_request") as request:
            self.assertEqual(fanart.artwork(MOVIE), {})
        request.assert_not_called()

    def test_picks_the_site_language_then_the_most_liked(self):
        data = {
            "hdmovielogo": [
                {"url": "de.png", "lang": "de", "likes": "9"},
                {"url": "en-low.png", "lang": "en", "likes": "1"},
                {"url": "en-top.png", "lang": "en", "likes": "5"},
            ],
            "movieposter": [{"url": "none.jpg", "lang": "00", "likes": "3"}],
        }
        with patch("app.providers.services.api_request", return_value=data) as request:
            art = fanart.artwork(MOVIE)

        self.assertEqual(art, {"logo": "en-top.png", "poster": "none.jpg"})
        self.assertEqual(request.call_args.args[2], f"{fanart.BASE_URL}/movies/238")

    def test_a_result_is_cached_and_the_shell_never_fetches(self):
        self.assertIsNone(fanart.artwork(MOVIE, allow_network=False))
        with patch("app.providers.services.api_request", return_value={}) as request:
            fanart.artwork(MOVIE)
            fanart.artwork(MOVIE)
        request.assert_called_once()
        self.assertEqual(fanart.artwork(MOVIE, allow_network=False), {})

    def test_a_title_without_art_is_cached_as_empty(self):
        with patch("app.providers.services.api_request", side_effect=_not_found()):
            self.assertEqual(fanart.artwork(MOVIE), {})
        self.assertEqual(cache.get("fanart_v1_movies_238"), {})

    def test_tmdb_shows_use_their_tvdb_id(self):
        show = {
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "media_id": "1399",
            "provider_external_ids": {"tvdb_id": 121361},
        }
        with patch("app.providers.services.api_request", return_value={}) as request:
            fanart.artwork(show)
            self.assertEqual(fanart.artwork({**show, "provider_external_ids": {}}), {})

        request.assert_called_once()
        self.assertEqual(request.call_args.args[2], f"{fanart.BASE_URL}/tv/121361")


@override_settings(FANART_API_KEY="test-key")
class FanartDetailPageTests(TestCase):
    """The v2 movie page shows fanart.tv's logo, poster and background."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="fanart",
            password="12345",
            theme=ThemeChoices.CINETRACK,
        )
        self.client.force_login(self.user)
        self.url = reverse(
            "media_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "238",
                "title": "test-movie",
            },
        )
        patcher = patch("app.providers.services.get_media_metadata")
        self.addCleanup(patcher.stop)
        patcher.start().return_value = {
            **MOVIE,
            "title": "Test Movie",
            "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
            "details": {"status": "Released"},
        }

    def test_cached_art_renders_in_the_shell(self):
        cache.set("fanart_v1_movies_238", {"logo": LOGO, "poster": POSTER, "background": BACKGROUND})

        response = self.client.get(self.url)

        self.assertContains(response, 'class="ct-detail-title ct-detail-title--logo"')
        self.assertContains(response, LOGO)
        self.assertContains(response, POSTER)
        self.assertContains(response, BACKGROUND)
        self.assertNotContains(response, "ct_fanart=1")

    def test_a_miss_is_fetched_by_the_secondary_fragment(self):
        with patch("app.providers.services.api_request") as request:
            shell = self.client.get(self.url)
        request.assert_not_called()
        self.assertContains(shell, "ct_fanart=1")
        self.assertContains(shell, 'id="ct-detail-backdrop-pending"')

        data = {
            "hdmovielogo": [{"url": LOGO, "lang": "en", "likes": "1"}],
            "movieposter": [{"url": POSTER, "lang": "en", "likes": "1"}],
            "moviebackground": [{"url": BACKGROUND, "lang": "", "likes": "1"}],
        }
        with patch("app.providers.services.api_request", return_value=data):
            fragment = self.client.get(f"{self.url}?fragment=secondary&ct_fanart=1")

        html = fragment.content.decode()
        self.assertIn('hx-swap-oob="outerHTML:#ct-detail-backdrop-pending"', html)
        self.assertIn(BACKGROUND, html)
        self.assertIn('id="ct-detail-poster-img"', html)
        self.assertIn(POSTER, html)
        self.assertIn('id="ct-detail-title"', html)
        self.assertIn(LOGO, html)

    @override_settings(FANART_API_KEY="")
    def test_without_a_key_the_page_is_unchanged(self):
        response = self.client.get(self.url)

        self.assertContains(response, '<h1 class="ct-detail-title" id="ct-detail-title">Test Movie</h1>')
        self.assertNotContains(response, "ct_fanart=1")
