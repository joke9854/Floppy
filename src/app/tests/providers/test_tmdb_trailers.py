"""P8 Trailers row: every trailer and teaser of a title and its seasons."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app import carousel
from app.models import MediaTypes, Sources
from app.providers import tmdb


def _video(key, kind, published="2024-01-01"):
    return {"site": "YouTube", "key": key, "type": kind, "name": f"{kind} {key}", "published_at": published}


class ParseCarouselVideosTests(TestCase):
    def test_trailers_then_teasers_newest_first(self):
        response = {
            "videos": {
                "results": [
                    _video("old", "Trailer", "2020-01-01"),
                    _video("tease", "Teaser", "2025-01-01"),
                    _video("new", "Trailer", "2024-01-01"),
                    _video("bts", "Behind the Scenes"),
                    {"site": "Vimeo", "key": "x", "type": "Trailer"},
                ],
            },
        }

        keys = [video["key"] for video in tmdb._parse_carousel_videos(response)]

        self.assertEqual(keys, ["new", "old", "tease"])

    def test_without_trailers_any_youtube_video_stands_in(self):
        response = {"videos": {"results": [_video("clip", "Clip")]}}

        self.assertEqual([v["key"] for v in tmdb._parse_carousel_videos(response)], ["clip"])


class ResolveTrailersTests(TestCase):
    @patch("app.providers.tmdb.tv")
    @patch("app.providers.tmdb.carousel_media")
    def test_show_lists_its_own_then_newest_seasons_without_duplicates(self, carousel_media, tv):
        tv.return_value = {"related": {"seasons": [{"season_number": n} for n in (0, 1, 2)]}}
        videos = {
            None: [{"key": "show", "name": "", "type": "Trailer"}],
            2: [{"key": "s2", "name": "", "type": "Trailer"}, {"key": "show", "name": "", "type": "Trailer"}],
            1: [{"key": "clip", "name": "", "type": "Featurette"}],
        }
        carousel_media.side_effect = lambda _type, _id, season_number=None: {"videos": videos[season_number]}

        trailers = carousel.resolve_trailers(MediaTypes.TV.value, Sources.TMDB.value, "95396")

        self.assertEqual([(t["key"], t["season"]) for t in trailers], [("show", None), ("s2", 2)])

    def test_other_sources_have_none(self):
        self.assertEqual(carousel.resolve_trailers(MediaTypes.TV.value, Sources.TVDB.value, "1"), [])


class TrailersFragmentTests(TestCase):
    def setUp(self):
        cache.clear()
        user = get_user_model().objects.create_user(username="trailers", password="12345")
        self.client.force_login(user)

    @patch("app.carousel.resolve_trailers", return_value=[{"key": "abc123", "name": "Official Trailer", "type": "Trailer", "season": None}])
    def test_fragment_renders_row_and_swaps_in_the_hero_button(self, _resolve):
        url = reverse("media_details", args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "550", "fight-club"])

        content = self.client.get(url, {"fragment": "trailers"}).content.decode()

        self.assertIn("Official Trailer", content)
        self.assertIn('id="ct-trailer-slot" class="contents" hx-swap-oob="true"', content)
        self.assertIn("abc123", content)

    @patch("app.carousel.resolve_trailers", return_value=[])
    def test_no_trailers_renders_nothing(self, _resolve):
        url = reverse("media_details", args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "550", "fight-club"])

        self.assertEqual(self.client.get(url, {"fragment": "trailers"}).content, b"")
