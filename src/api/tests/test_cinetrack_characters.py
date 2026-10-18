"""Tests for the read-only CineTrack characters endpoint."""

from unittest.mock import patch

from django.core.cache import cache

from app.providers import services

from .base import FloppyApiTestCase

URL_NAME = "api_media_characters"
VIEWS = "api.cinetrack_character_views"

SERIES_EXTENDED = {
    "characters": [
        {
            "name": "Walter White",
            "personName": "Bryan Cranston",
            "peopleId": 101,
            "type": 3,
            "peopleType": "Actor",
            "image": "https://artworks.thetvdb.com/banners/characters/walter.jpg",
            "personImgURL": "/banners/person/101.jpg",
            "sort": 1,
        },
        {"name": "", "personName": "Vince Gilligan", "peopleId": 7, "type": 6, "peopleType": "Creator", "sort": 0},
        {"name": "Jesse Pinkman", "personName": "Aaron Paul", "peopleId": 102, "type": 3, "image": None, "sort": 2},
        {"name": "Guest", "personName": "Guest Star", "peopleId": 103, "peopleType": "Guest Star", "image": ""},
    ],
}


class CharactersTests(FloppyApiTestCase):
    """Characters come from TVDB; nothing is written."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def fetch(self, media_type="tv", source="tmdb", media_id="1396", headers=True):
        return self.call_api(
            "get",
            URL_NAME,
            args=(media_type, source, media_id),
            headers=self.auth_headers if headers else None,
        )

    def test_tv_characters_keep_character_and_actor_images(self):
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.tv", return_value={"tvdb_id": "81189"}),
            patch(f"{VIEWS}.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="81189"),
            patch("app.providers.tvdb._get_series_extended", return_value=SERIES_EXTENDED) as extended,
        ):
            response = self.fetch()

        self.assertEqual(response.status_code, 200)
        extended.assert_called_once_with("81189")
        body = response.json()
        self.assertEqual(body["tvdb_id"], "81189")
        self.assertEqual(
            [row["name"] for row in body["characters"]],
            ["Walter White", "Jesse Pinkman", "Guest"],
        )
        walter = body["characters"][0]
        self.assertEqual(walter["person_name"], "Bryan Cranston")
        self.assertEqual(walter["character_image"], "https://artworks.thetvdb.com/banners/characters/walter.jpg")
        self.assertEqual(walter["person_image"], "https://artworks.thetvdb.com/banners/person/101.jpg")
        self.assertIsNone(body["characters"][1]["character_image"])
        self.assertIsNone(body["characters"][2]["character_image"])

    def test_tvdb_source_skips_tmdb(self):
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.tv") as tmdb_tv,
            patch("app.providers.tvdb._get_series_extended", return_value=SERIES_EXTENDED),
        ):
            response = self.fetch(source="tvdb", media_id="81189")

        self.assertEqual(response.status_code, 200)
        tmdb_tv.assert_not_called()
        self.assertEqual(len(response.json()["characters"]), 3)

    def test_movie_resolves_tvdb_id_through_imdb(self):
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.movie", return_value={"provider_external_ids": {"imdb_id": "tt0133093"}}),
            patch("app.providers.tvdb.search_remote_id", return_value=[{"series": {"id": 1}}, {"movie": {"id": 169}}]),
            patch("app.providers.tvdb._get_movie_extended", return_value=SERIES_EXTENDED) as extended,
        ):
            response = self.fetch(media_type="movie", media_id="603")

        self.assertEqual(response.status_code, 200)
        extended.assert_called_once_with("169")
        self.assertEqual(response.json()["tvdb_id"], "169")

    def test_no_tvdb_key_returns_empty_list(self):
        with patch(f"{VIEWS}.tvdb.enabled", return_value=False):
            response = self.fetch()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"tvdb_id": None, "reason": "tvdb_not_configured", "characters": []})

    def test_no_tvdb_match_returns_empty_list(self):
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.tv", return_value={}),
            patch(f"{VIEWS}.tmdb.resolve_tvdb_id_for_tmdb_show", return_value=None),
        ):
            response = self.fetch()

        self.assertEqual(response.json()["reason"], "no_tvdb_match")

    def test_provider_failure_is_503(self):
        error = services.ProviderAPIError("tvdb", Exception("down"))
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.tv", side_effect=error),
        ):
            response = self.fetch()

        self.assertEqual(response.status_code, 503)

    def test_rejects_unsupported_media_type_and_source(self):
        self.assertEqual(self.fetch(media_type="anime").status_code, 400)
        self.assertEqual(self.fetch(source="mal").status_code, 400)

    def test_requires_authentication(self):
        self.assertIn(self.fetch(headers=False).status_code, {401, 403})
