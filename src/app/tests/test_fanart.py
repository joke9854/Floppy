from unittest.mock import patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app import backdrops, image_cache
from app.models import Item, MediaTypes, Sources
from app.providers import credentials, fanart
from app.providers.services import ProviderAPIError
from app.templatetags.app_tags import ct_poster
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

    @override_settings(FANART_API_KEY="")
    def test_a_key_saved_in_settings_metadata_enables_it(self):
        credentials.set_instance("fanart", {"api_key": "saved-key"})
        self.addCleanup(credentials.clear_instance, "fanart")

        with patch("app.providers.services.api_request", return_value={}) as request:
            fanart.artwork(MOVIE)

        self.assertEqual(request.call_args.kwargs["params"], {"api_key": "saved-key"})

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
        self.assertEqual(cache.get("fanart_v2_tmdb_movies_238"), {})

    def test_tmdb_shows_use_their_tvdb_id(self):
        show = {
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "media_id": "1399",
            "provider_external_ids": {"tvdb_id": 121361},
        }
        with patch("app.providers.services.api_request", return_value={}) as request:
            fanart.artwork(show)

        request.assert_called_once()
        self.assertEqual(request.call_args.args[2], f"{fanart.BASE_URL}/tv/121361")

    def test_a_show_page_without_ids_is_a_miss_then_resolves_its_tvdb_id(self):
        """The detail shell's show payload has no external ids (the prod bug)."""
        show = {"source": Sources.TMDB.value, "media_type": MediaTypes.TV.value, "media_id": "61889"}
        data = {"hdtvlogo": [{"url": LOGO, "lang": "en", "likes": "1"}]}

        self.assertIsNone(fanart.artwork(show, allow_network=False))
        with (
            patch("app.providers.tmdb.external_ids", return_value={"tvdb_id": 281662}) as ids,
            patch("app.providers.services.api_request", return_value=data) as request,
        ):
            self.assertEqual(fanart.artwork(show), {"logo": LOGO})

        ids.assert_called_once_with(MediaTypes.TV.value, "61889")
        self.assertEqual(request.call_args.args[2], f"{fanart.BASE_URL}/tv/281662")
        self.assertEqual(fanart.artwork(show, allow_network=False), {"logo": LOGO})

    def test_a_show_without_a_tvdb_id_is_cached_as_empty(self):
        show = {"source": Sources.TMDB.value, "media_type": MediaTypes.TV.value, "media_id": "5"}
        with (
            patch("app.providers.tmdb.external_ids", return_value={}),
            patch("app.providers.services.api_request") as request,
        ):
            self.assertEqual(fanart.artwork(show), {})
        request.assert_not_called()
        self.assertEqual(fanart.artwork(show, allow_network=False), {})


@override_settings(FANART_API_KEY="test-key")
class FanartEverywhereTests(TestCase):
    """Grids, rows and backdrops use cached fanart.tv art and warm misses."""

    def setUp(self):
        cache.clear()
        self.show = Item.objects.create(
            media_id="61889",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Daredevil",
            image="https://image.tmdb.org/t/p/w500/tmdb.jpg",
        )
        self.episode = Item.objects.create(
            media_id="61889",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Daredevil",
            season_number=1,
            episode_number=1,
        )

    def test_a_miss_is_fetched_in_the_background_then_cached_art_is_used(self):
        data = {
            "tvposter": [{"url": POSTER, "lang": "en", "likes": "1"}],
            "showbackground": [{"url": BACKGROUND, "lang": "", "likes": "1"}],
        }
        with (
            patch("app.providers.tmdb.external_ids", return_value={"tvdb_id": 281662}),
            patch("app.providers.services.api_request", return_value=data) as request,
            self.captureOnCommitCallbacks(execute=True),
        ):
            self.assertIsNone(fanart.cached(self.show, "poster"))
            self.assertIsNone(fanart.cached(self.show, "background"))

        request.assert_called_once()
        self.assertEqual(fanart.cached(self.show, "poster"), POSTER)
        # An episode shares its show's background.
        self.assertEqual(backdrops.cached_backdrop(self.episode), BACKGROUND)

    def test_grid_posters_use_fanart_only_through_the_resizing_image_cache(self):
        cache.set("fanart_v2_tmdb_tv_61889", {"poster": POSTER})

        image_cache.set_enabled(False)
        self.assertEqual(ct_poster(self.show), self.show.image)
        image_cache.set_enabled(True)
        self.assertEqual(ct_poster(self.show), POSTER)
        self.assertEqual(ct_poster("https://example.com/override.jpg"), "https://example.com/override.jpg")

    @override_settings(FANART_API_KEY="")
    def test_without_a_key_cards_keep_their_own_art(self):
        cache.set("fanart_v2_tmdb_tv_61889", {"poster": POSTER, "background": BACKGROUND})
        image_cache.set_enabled(True)

        with patch("app.providers.services.api_request") as request:
            self.assertEqual(ct_poster(self.show), self.show.image)
            self.assertIsNone(fanart.cached(self.show, "background"))
        request.assert_not_called()

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
        cache.set("fanart_v2_tmdb_movies_238", {"logo": LOGO, "poster": POSTER, "background": BACKGROUND})

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
