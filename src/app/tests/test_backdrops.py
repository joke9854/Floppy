"""Tests for app.backdrops, the shared horizontal-artwork resolver.

The resolution rules themselves (TMDB movie/tv, show-level mapping for
episodes/seasons/anime, the TVDB→TMDB cross-reference, IGDB games) are
exercised through the web-UI wrapper in test_statistics_cache.py. What is
covered here is the API-facing contract that wrapper cannot express: a missing
backdrop is None, never a poster.
"""

from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app import backdrops
from app.models import MediaTypes, Sources

BACKDROP_URL = "https://image.tmdb.org/t/p/w1280/backdrop.jpg"
PORTRAIT_POSTER = "https://image.tmdb.org/t/p/w500/poster.jpg"


def _tv_item(**overrides):
    item = {
        "source": Sources.TMDB.value,
        "media_type": MediaTypes.TV.value,
        "media_id": "1396",
        "image": PORTRAIT_POSTER,
    }
    item.update(overrides)
    return item


class ResolveBackdropTests(TestCase):
    """resolve_backdrop must report absence rather than substituting a poster."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_returns_none_for_missing_item(self):
        self.assertIsNone(backdrops.resolve_backdrop(None))

    def test_returns_none_when_item_has_no_provider_identity(self):
        """Manual entries have no source, so there is nothing to look up."""
        item = {"media_type": MediaTypes.MOVIE.value, "image": PORTRAIT_POSTER}
        self.assertIsNone(backdrops.resolve_backdrop(item))

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=None)
    def test_returns_none_instead_of_poster_when_provider_has_no_backdrop(
        self,
        mock_backdrop,
    ):
        result = backdrops.resolve_backdrop(_tv_item())

        self.assertIsNone(result)
        mock_backdrop.assert_called_once_with(MediaTypes.TV.value, "1396")

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=settings.IMG_NONE)
    def test_placeholder_image_counts_as_no_backdrop(self, mock_backdrop):
        """The IMG_NONE placeholder is not real artwork, so it must not be served."""
        self.assertIsNone(backdrops.resolve_backdrop(_tv_item()))

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=BACKDROP_URL)
    def test_returns_backdrop_when_provider_has_one(self, mock_backdrop):
        self.assertEqual(backdrops.resolve_backdrop(_tv_item()), BACKDROP_URL)

    @patch("lists.models.CustomList._get_tmdb_backdrop")
    def test_allow_network_false_never_calls_the_provider(self, mock_backdrop):
        """Callers on a hot path must not block on TMDB when the cache is cold."""
        result = backdrops.resolve_backdrop(_tv_item(), allow_network=False)

        self.assertIsNone(result)
        mock_backdrop.assert_not_called()

    @patch("lists.models.CustomList._get_tmdb_backdrop")
    def test_allow_network_false_still_serves_a_cached_backdrop(self, mock_backdrop):
        cache.set("tmdb_backdrop_tv_1396", BACKDROP_URL, 60)

        result = backdrops.resolve_backdrop(_tv_item(), allow_network=False)

        self.assertEqual(result, BACKDROP_URL)
        mock_backdrop.assert_not_called()

    @patch("lists.models.CustomList._get_tmdb_backdrop", side_effect=RuntimeError)
    def test_provider_failure_is_not_fatal(self, mock_backdrop):
        """Artwork is decoration; a provider outage must not fail the response."""
        self.assertIsNone(backdrops.resolve_backdrop(_tv_item()))

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=BACKDROP_URL)
    def test_season_resolves_against_its_show(self, mock_backdrop):
        """Seasons share their show's media_id and have no backdrop of their own."""
        item = _tv_item(media_type=MediaTypes.SEASON.value)

        self.assertEqual(backdrops.resolve_backdrop(item), BACKDROP_URL)
        mock_backdrop.assert_called_once_with(MediaTypes.TV.value, "1396")

    @patch("lists.models.CustomList._get_igdb_backdrop", return_value=BACKDROP_URL)
    def test_igdb_game_uses_the_igdb_getter(self, mock_backdrop):
        item = _tv_item(
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            media_id="1020",
        )

        self.assertEqual(backdrops.resolve_backdrop(item), BACKDROP_URL)
        mock_backdrop.assert_called_once_with("1020")

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=BACKDROP_URL)
    def test_tvdb_item_uses_its_tmdb_cross_reference(self, mock_backdrop):
        item = _tv_item(
            source=Sources.TVDB.value,
            media_id="81189",
            provider_external_ids={"tmdb_id": "1396"},
        )

        self.assertEqual(backdrops.resolve_backdrop(item), BACKDROP_URL)
        mock_backdrop.assert_called_once_with(MediaTypes.TV.value, "1396")

    @patch("lists.models.CustomList._get_tmdb_backdrop")
    def test_tvdb_item_without_cross_reference_returns_none(self, mock_backdrop):
        """No TMDB counterpart means no backdrop source at all."""
        item = _tv_item(source=Sources.TVDB.value, media_id="81189")

        self.assertIsNone(backdrops.resolve_backdrop(item))
        mock_backdrop.assert_not_called()

    @patch("lists.models.CustomList._get_tmdb_backdrop", return_value=BACKDROP_URL)
    def test_accepts_model_instances_as_well_as_dicts(self, mock_backdrop):
        from app.models import Item

        item = Item(
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            media_id="1396",
            image=PORTRAIT_POSTER,
        )

        self.assertEqual(backdrops.resolve_backdrop(item), BACKDROP_URL)


class QueueBackdropFetchTests(TestCase):
    """queue_backdrop_fetch queues true misses only, once per key."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def _queue(self, item):
        with (
            patch("app.tasks.fetch_backdrop.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            backdrops.queue_backdrop_fetch(item)
            backdrops.queue_backdrop_fetch(item)
        return delay

    def test_miss_is_queued_once(self):
        delay = self._queue(_tv_item())

        delay.assert_called_once_with(
            {
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.TV.value,
                "media_id": "1396",
                "provider_external_ids": None,
            },
        )

    def test_known_absence_is_not_queued(self):
        cache.set("tmdb_backdrop_tv_1396", settings.IMG_NONE)

        self._queue(_tv_item()).assert_not_called()

    def test_item_without_a_backdrop_source_is_not_queued(self):
        self._queue({"media_type": MediaTypes.MOVIE.value}).assert_not_called()
