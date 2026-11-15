"""FORK (P1-D): start, read and stop rewatch passes through the API."""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.utils import timezone

from app.models import TV, Episode, Item, MediaTypes, Season, Sources, Status

from .base import FloppyApiTestCase

METADATA_PATH = "app.providers.services.get_media_metadata"
SEASON_METADATA = {
    "episodes": [{"episode_number": 1}, {"episode_number": 2}],
    "max_progress": 2,
    "image": "s.jpg",
    "season/1": {"episodes": [{"episode_number": 1}, {"episode_number": 2}]},
}
SHOW_ID = "880123"


@patch(METADATA_PATH, return_value=SEASON_METADATA)
class RewatchApiTests(FloppyApiTestCase):
    """A show whose only season was fully watched in June 2023."""

    def setUp(self):
        super().setUp()
        tv_item = Item.objects.create(
            media_id=SHOW_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Show",
        )
        self.tv = TV.objects.create(
            item=tv_item, user=self.user1, status=Status.IN_PROGRESS.value
        )
        season_item = Item.objects.create(
            media_id=SHOW_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Show",
            season_number=1,
        )
        self.season = Season.objects.create(
            item=season_item,
            user=self.user1,
            related_tv=self.tv,
            status=Status.IN_PROGRESS.value,
        )
        for episode_number in (1, 2):
            item = Item.objects.create(
                media_id=SHOW_ID,
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title="Show",
                season_number=1,
                episode_number=episode_number,
            )
            with patch(METADATA_PATH, return_value=SEASON_METADATA):
                Episode.objects.create(
                    item=item,
                    related_season=self.season,
                    end_date=datetime(2023, 6, episode_number, tzinfo=UTC),
                )
        self.plays_before = Episode.objects.filter(related_season=self.season).count()

    def _show(self, method, payload=None, media_id=SHOW_ID):
        return self.call_api(
            method,
            "api_show_rewatch",
            args=("tv", Sources.TMDB.value, media_id),
            payload=payload,
            headers=self.auth_headers,
        )

    def _season(self, method, payload=None):
        return self.call_api(
            method,
            "api_season_rewatch",
            args=("tv", Sources.TMDB.value, SHOW_ID, 1),
            payload=payload,
            headers=self.auth_headers,
        )

    def test_start_read_and_stop_a_show_rewatch(self, _metadata):
        started_at = "2024-01-02T20:15:30+01:00"

        started = self._show("post", {"started_at": started_at})

        self.assertEqual(started.status_code, HTTP.OK)
        body = started.json()
        self.assertTrue(body["rewatching"])
        self.assertEqual(body["skipped_seasons"], [])
        self.season.refresh_from_db()
        # The exact instant, not the day.
        self.assertEqual(
            self.season.rewatch_started_at, datetime(2024, 1, 2, 19, 15, 30, tzinfo=UTC)
        )
        read = self._show("get").json()
        self.assertEqual(read["seasons"][0]["season_number"], 1)
        self.assertIsNotNone(read["seasons"][0]["started_at"])

        stopped = self._show("delete")

        self.assertEqual(stopped.status_code, HTTP.OK)
        self.assertFalse(stopped.json()["rewatching"])
        self.season.refresh_from_db()
        self.assertIsNone(self.season.rewatch_started_at)
        self.assertEqual(
            Episode.objects.filter(related_season=self.season).count(),
            self.plays_before,
        )

    def test_season_rewatch_defaults_to_now(self, _metadata):
        before = timezone.now()
        response = self._season("post", {})
        self.assertEqual(response.status_code, HTTP.OK)
        self.season.refresh_from_db()
        self.assertGreaterEqual(self.season.rewatch_started_at, before)
        self.assertTrue(self._season("get").json()["rewatching"])

    def test_second_start_is_a_conflict(self, _metadata):
        self.assertEqual(self._show("post", {}).status_code, HTTP.OK)
        again = self._show("post", {})
        self.assertEqual(again.status_code, HTTP.CONFLICT)
        self.assertEqual(again.json()["code"], "conflict")
        self.assertEqual(again.json()["detail"], "Every season is already being rewatched.")

    def test_already_watched_from_that_date_is_a_conflict(self, _metadata):
        response = self._show("post", {"started_at": "2023-05-01T00:00:00+00:00"})
        self.assertEqual(response.status_code, HTTP.CONFLICT)
        self.season.refresh_from_db()
        self.assertIsNone(self.season.rewatch_started_at)

    def test_bad_start_dates_are_400(self, _metadata):
        future = (timezone.now() + timedelta(days=1)).isoformat()
        for value in ("2024-01-02", "2024-01-02T20:00:00", "yesterday", future, 5):
            with self.subTest(value=value):
                response = self._show("post", {"started_at": value})
                self.assertEqual(response.status_code, HTTP.BAD_REQUEST)

    def test_untracked_or_wrong_type_is_rejected(self, _metadata):
        self.assertEqual(self._show("get", media_id="1").status_code, HTTP.NOT_FOUND)
        movie = self.call_api(
            "get",
            "api_show_rewatch",
            args=("movie", Sources.TMDB.value, SHOW_ID),
            headers=self.auth_headers,
        )
        self.assertEqual(movie.status_code, HTTP.BAD_REQUEST)
