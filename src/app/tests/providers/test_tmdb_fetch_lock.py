"""One uncached TMDB detail fetch per show/movie at a time on the request path."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from app.providers import services, tmdb

TV_DATA = {"title": "Show", "tvdb_id": 1, "related": {"seasons": []}}


class TmdbFetchLockTests(TestCase):
    def setUp(self):
        cache.clear()

    def _hold_lock(self, cache_key):
        lock_key = f"{cache_key}_fetch_lock"
        cache.add(lock_key, True, tmdb.FETCH_LOCK_TIMEOUT)
        return lock_key

    @patch("app.providers.tmdb.process_tv", return_value=TV_DATA)
    @patch("app.providers.tmdb.services.api_request")
    def test_tv_waits_for_the_lock_holders_cache_fill(self, mock_api, _process):
        cache_key = tmdb._tv_cache_key(1399)
        lock_key = self._hold_lock(cache_key)

        def holder_finishes(_seconds):
            cache.set(cache_key, TV_DATA)
            cache.delete(lock_key)

        with patch("app.providers.tmdb.time.sleep", side_effect=holder_finishes):
            self.assertEqual(tmdb.tv(1399)["title"], "Show")

        mock_api.assert_not_called()

    @patch("app.providers.tmdb.process_tv", return_value=TV_DATA)
    @patch("app.providers.tmdb.services.api_request", return_value={})
    def test_tv_fetches_itself_when_the_lock_holder_fails(self, mock_api, _process):
        cache_key = tmdb._tv_cache_key(1399)
        lock_key = self._hold_lock(cache_key)

        with patch(
            "app.providers.tmdb.time.sleep",
            side_effect=lambda _seconds: cache.delete(lock_key),
        ):
            self.assertEqual(tmdb.tv(1399)["title"], "Show")

        mock_api.assert_called_once()

    @patch(
        "app.providers.tmdb.services.api_request",
        side_effect=services.ProviderAPIError("tmdb", Exception("stalled")),
    )
    @patch("app.providers.tmdb.FETCH_WAIT_SECONDS", 0)
    def test_movie_fetches_itself_once_the_wait_cap_passes(self, mock_api):
        lock_key = self._hold_lock(tmdb._movie_cache_key(603))

        with self.assertRaises(services.ProviderAPIError):
            tmdb.movie(603)

        mock_api.assert_called_once()
        # The waiter never owned the lock, so it leaves the holder's lock alone.
        self.assertIsNotNone(cache.get(lock_key))

    @patch(
        "app.providers.tmdb.services.api_request",
        side_effect=services.ProviderAPIError("tmdb", Exception("stalled")),
    )
    def test_failed_fetch_releases_the_lock(self, _mock_api):
        cache_key = tmdb._tv_cache_key(1399)

        with self.assertRaises(services.ProviderAPIError):
            tmdb.tv(1399)

        self.assertIsNone(cache.get(f"{cache_key}_fetch_lock"))

    @patch("app.providers.tmdb.fetch_and_cache_seasons")
    def test_tv_with_seasons_waits_for_the_lock_holders_seasons(self, mock_fetch):
        tv_cache_key = tmdb._tv_cache_key(1399)
        lock_key = self._hold_lock(f"{tv_cache_key}_seasons_1")

        def holder_finishes(_seconds):
            cache.set(tv_cache_key, TV_DATA)
            cache.set(tmdb._season_cache_key(1399, 1), {"season_number": 1})
            cache.delete(lock_key)

        with patch("app.providers.tmdb.time.sleep", side_effect=holder_finishes):
            data = tmdb.tv_with_seasons(1399, [1])

        mock_fetch.assert_not_called()
        self.assertEqual(data["title"], "Show")
        self.assertEqual(data["season/1"], {"season_number": 1})
