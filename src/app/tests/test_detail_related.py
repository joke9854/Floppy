"""Show pages enrich season cards from the cache and fetch the rest later."""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from app.detail_related import enrich_detail_seasons
from app.models import Sources
from app.providers import tmdb


class EnrichDetailSeasonsTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = patch(
            "app.services.metadata_resolution.metadata_language_default",
            return_value="en",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        cache.clear()

    def _enrich(self, source=Sources.TMDB.value):
        metadata = {
            "title": "Show",
            "related": {"seasons": [{"season_number": 1}, {"season_number": 2}]},
        }
        with (
            patch(
                "app.providers.services.get_media_metadata",
                return_value={"season/1": {"season_title": "Season One"}},
            ) as fetch,
            patch("app.tasks.fetch_tmdb_seasons.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            enrich_detail_seasons(
                metadata,
                media_id="99",
                source=source,
                user=None,
                detail_item=None,
                render_secondary_only=True,
            )
        return fetch, delay, metadata

    def test_tmdb_uses_cached_seasons_and_queues_the_rest(self):
        cache.set(tmdb._season_cache_key("99", 1, "en"), {"max_progress": 10})

        fetch, delay, metadata = self._enrich()

        self.assertEqual(fetch.call_args.args[3], [1])
        delay.assert_called_once()
        self.assertEqual(delay.call_args.args[:3], ("99", [2], "en"))
        self.assertEqual(
            metadata["related"]["seasons"][0]["season_title"], "Season One"
        )

    def test_nothing_cached_makes_no_provider_call(self):
        fetch, delay, _metadata = self._enrich()

        fetch.assert_not_called()
        self.assertEqual(delay.call_args.args[1], [1, 2])

    def test_a_queued_fetch_is_not_queued_again(self):
        self._enrich()
        _fetch, delay, _metadata = self._enrich()

        delay.assert_not_called()

    def test_tvdb_still_fetches_on_the_request(self):
        fetch, delay, _metadata = self._enrich(source=Sources.TVDB.value)

        self.assertEqual(fetch.call_args.args[3], [1, 2])
        delay.assert_not_called()
