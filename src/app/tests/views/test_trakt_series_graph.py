from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from app.models import Item, MediaTypes, Sources
from app.views import trakt_series_graph_fragment


class TraktSeriesGraphFragmentTests(TestCase):
    """Coverage for Trakt series graph polling behavior."""

    def test_specials_do_not_keep_show_graph_polling(self):
        """Season 0 episodes should not hold the show-level poll open."""
        Item.objects.create(
            media_id="show-1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Special 1",
            season_number=0,
            episode_number=1,
        )
        Item.objects.create(
            media_id="show-1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Episode 1",
            season_number=1,
            episode_number=1,
            trakt_rating=8.0,
            trakt_rating_count=100,
        )

        request = RequestFactory().get("/app/api/trakt-series-graph/tmdb/show-1/")
        response = trakt_series_graph_fragment(request, Sources.TMDB.value, "show-1")

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("every 5s", content)
        self.assertNotIn("Fetching remaining episodes", content)

    def _unrated(self, episode_number, release_datetime):
        return Item.objects.create(
            media_id="show-2",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title=f"Episode {episode_number}",
            season_number=1,
            episode_number=episode_number,
            release_datetime=release_datetime,
        )

    def _render(self, query=""):
        request = RequestFactory().get(f"/api/trakt-series-graph/tmdb/show-2/{query}")
        return trakt_series_graph_fragment(
            request, Sources.TMDB.value, "show-2",
        ).content.decode()

    def test_unaired_or_undated_episodes_do_not_keep_polling(self):
        self._unrated(1, timezone.now() + timedelta(days=7))
        self._unrated(2, None)

        self.assertNotIn("every 5s", self._render())

    def test_aired_unrated_episode_keeps_polling_until_cap(self):
        self._unrated(1, timezone.now() - timedelta(days=1))

        self.assertIn("every 5s", self._render())
        self.assertIn("?n=1", self._render())
        self.assertNotIn("every 5s", self._render("?n=24"))
