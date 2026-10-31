"""Tests for the read-only CineTrack characters endpoint."""

from unittest.mock import patch

from django.core.cache import cache

from app.providers import services, tmdb

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
            patch(f"{VIEWS}.tmdb.external_ids", return_value={"tvdb_id": 81189}),
            patch(f"{VIEWS}.tmdb.tv") as tmdb_tv,
            patch("app.providers.tvdb._series_characters_payload", return_value=SERIES_EXTENDED) as extended,
        ):
            response = self.fetch()

        self.assertEqual(response.status_code, 200)
        extended.assert_called_once_with("81189")
        tmdb_tv.assert_not_called()
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
            patch(f"{VIEWS}.tmdb.external_ids") as tmdb_tv,
            patch("app.providers.tvdb._series_characters_payload", return_value=SERIES_EXTENDED),
        ):
            response = self.fetch(source="tvdb", media_id="81189")

        self.assertEqual(response.status_code, 200)
        tmdb_tv.assert_not_called()
        self.assertEqual(len(response.json()["characters"]), 3)

    def test_movie_resolves_tvdb_id_through_imdb(self):
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.external_ids", return_value={"imdb_id": "tt0133093"}),
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
            patch(f"{VIEWS}.tmdb.external_ids", return_value={}),
            patch(f"{VIEWS}.tmdb.tv", return_value={}),
            patch(f"{VIEWS}.tmdb.resolve_tvdb_id_for_tmdb_show", return_value=None) as resolve,
        ):
            response = self.fetch()

        self.assertEqual(response.json()["reason"], "no_tvdb_match")
        resolve.assert_called_once()

    def test_provider_failure_is_503(self):
        error = services.ProviderAPIError("tvdb", Exception("down"))
        with (
            patch(f"{VIEWS}.tvdb.enabled", return_value=True),
            patch(f"{VIEWS}.tmdb.external_ids", side_effect=error),
        ):
            response = self.fetch()

        self.assertEqual(response.status_code, 503)

    def test_rejects_unsupported_media_type_and_source(self):
        self.assertEqual(self.fetch(media_type="anime").status_code, 400)
        self.assertEqual(self.fetch(source="mal").status_code, 400)

    def test_requires_authentication(self):
        self.assertIn(self.fetch(headers=False).status_code, {401, 403})


class ExternalIdsTests(FloppyApiTestCase):
    """The characters lookup never fetches a full TMDB title."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_fetches_only_external_ids_once(self):
        payload = {"tvdb_id": 81189, "imdb_id": "tt0903747"}
        with patch("app.providers.tmdb.services.api_request", return_value=payload) as request:
            first = tmdb.external_ids("tv", "1396")
            second = tmdb.external_ids("tv", "1396")

        self.assertEqual(first["tvdb_id"], 81189)
        self.assertEqual(second, first)
        request.assert_called_once()
        self.assertTrue(request.call_args.args[2].endswith("/tv/1396/external_ids"))

    def test_reuses_a_cached_full_title(self):
        cache.set(tmdb._tv_cache_key("1396"), {"provider_external_ids": {"tvdb_id": 81189}})
        with patch("app.providers.tmdb.services.api_request") as request:
            ids = tmdb.external_ids("tv", "1396")

        self.assertEqual(ids["tvdb_id"], 81189)
        request.assert_not_called()


class MovieIdCacheTests(FloppyApiTestCase):
    """TVDB's slow remote-ID search runs once per IMDb id."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def test_match_and_miss_are_both_remembered(self):
        from app.providers import tvdb

        with patch("app.providers.tvdb.search_remote_id", return_value=[{"movie": {"id": 169}}]) as search:
            self.assertEqual(tvdb.movie_id_for_imdb("tt0133093"), "169")
            self.assertEqual(tvdb.movie_id_for_imdb("tt0133093"), "169")
        search.assert_called_once()

        with patch("app.providers.tvdb.search_remote_id", return_value=[]) as search:
            self.assertIsNone(tvdb.movie_id_for_imdb("tt0000001"))
            self.assertIsNone(tvdb.movie_id_for_imdb("tt0000001"))
        search.assert_called_once()


class CharacterRowsCacheTests(FloppyApiTestCase):
    """Character rows outlive their TVDB payload until a metadata refresh."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def read_twice_around(self, media_type, tvdb_id, refresh_keys):
        from app.providers import tvdb

        payload = {"data": SERIES_EXTENDED}
        with patch("app.providers.tvdb._request", return_value=payload) as request:
            first = tvdb.character_images(media_type, tvdb_id)
            # Payloads expire after 12h; the rows must not need them.
            cache.delete_many([
                tvdb._cache_key("series_extended_raw", tvdb_id),
                tvdb._cache_key("movie_extended", tvdb_id),
            ])
            self.assertEqual(tvdb.character_images(media_type, tvdb_id), first)
            self.assertEqual(request.call_count, 1)
            self.assertIn(tvdb.characters_cache_key(media_type, tvdb_id), refresh_keys())
            cache.delete_many(refresh_keys())
            tvdb.character_images(media_type, tvdb_id)
            self.assertEqual(request.call_count, 2)

    def test_tvdb_show_refresh_clears_rows(self):
        from app import metadata_utils

        self.read_twice_around(
            "tv", "81189", lambda: metadata_utils.provider_metadata_cache_keys("tvdb", "tv", "81189"),
        )

    def test_tmdb_show_refresh_clears_rows(self):
        from app import metadata_utils

        cache.set("tmdb_tv_1396_external_ids", {"tvdb_id": 81189})
        self.read_twice_around(
            "tv", "81189", lambda: metadata_utils.provider_metadata_cache_keys("tmdb", "tv", "1396"),
        )

    def test_tmdb_movie_refresh_clears_rows(self):
        from app import metadata_utils
        from app.providers import tvdb

        cache.set("tmdb_movie_603_external_ids", {"imdb_id": "tt0133093"})
        cache.set(tvdb._cache_key("movie_for_imdb", "tt0133093"), "169")
        self.read_twice_around(
            "movie", "169", lambda: metadata_utils.provider_metadata_cache_keys("tmdb", "movie", "603"),
        )
