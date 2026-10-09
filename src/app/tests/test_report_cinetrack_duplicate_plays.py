"""Tests for the read-only report_cinetrack_duplicate_plays command."""

from datetime import UTC, datetime, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from app.management.commands.report_cinetrack_duplicate_plays import classify_pair
from app.models import (
    TV,
    Episode,
    Item,
    MediaTypes,
    Movie,
    MoviePlay,
    Season,
    Sources,
    Status,
)

WATCHED = datetime(2025, 3, 4, 21, 15, 30, tzinfo=UTC)


class ClassifyPairTests(TestCase):
    """Pair classification mirrors Floppy's runtime-scaled duplicate window."""

    def test_within_runtime_window_is_near(self):
        self.assertEqual(
            classify_pair(WATCHED, WATCHED + timedelta(minutes=20), 25), "near"
        )

    def test_exact_whole_hour_gap_is_tz_offset(self):
        self.assertEqual(
            classify_pair(WATCHED, WATCHED + timedelta(hours=2), 25), "tz_offset"
        )

    def test_midnight_play_on_same_date_is_date_only(self):
        midnight = WATCHED.replace(hour=0, minute=0, second=0)
        self.assertEqual(classify_pair(midnight, WATCHED, 25), "date_only")

    def test_genuine_rewatch_days_apart_is_not_flagged(self):
        self.assertIsNone(
            classify_pair(WATCHED, WATCHED + timedelta(days=40, minutes=7), 25)
        )

    def test_non_whole_hour_gap_outside_window_is_not_flagged(self):
        self.assertIsNone(
            classify_pair(WATCHED, WATCHED + timedelta(hours=2, minutes=13), 25)
        )


class ReportCineTrackDuplicatePlaysTests(TestCase):
    """The command reports suspicious pairs and never writes."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="watcher", password="12345"
        )

    def _run(self, *args):
        out = StringIO()
        call_command("report_cinetrack_duplicate_plays", *args, stdout=out)
        return out.getvalue()

    def _episode(self, season, episode_item, end_date, operation_id=None):
        return Episode.objects.create(
            item=episode_item,
            related_season=season,
            end_date=end_date,
            watch_operation_id=operation_id,
        )

    def _episode_setup(self):
        tv_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Show",
        )
        tv = TV.objects.create(
            user=self.user, item=tv_item, status=Status.IN_PROGRESS.value
        )
        season_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Season 1",
            season_number=1,
        )
        season = Season.objects.create(
            user=self.user,
            item=season_item,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
        )
        episode_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Show",
            season_number=1,
            episode_number=2,
            runtime_minutes=25,
        )
        return season, episode_item

    def test_reports_episode_categories_with_origin_and_writes_nothing(self):
        season, episode_item = self._episode_setup()
        self._episode(
            season, episode_item, WATCHED, "11111111-1111-1111-1111-111111111111"
        )
        self._episode(season, episode_item, WATCHED + timedelta(hours=1))
        before = Episode.objects.count()

        output = self._run("--username", "watcher")

        self.assertIn("READ-ONLY REPORT", output)
        self.assertIn(
            "Episodes: 1 item(s) with 2+ plays; near=0, tz_offset=1, date_only=0",
            output,
        )
        self.assertIn("[tz_offset] Show S01E02", output)
        self.assertIn("[cinetrack]", output)
        self.assertIn("[other]", output)
        self.assertEqual(before, Episode.objects.count())

    def test_genuine_rewatch_is_not_reported(self):
        season, episode_item = self._episode_setup()
        self._episode(season, episode_item, WATCHED)
        self._episode(season, episode_item, WATCHED + timedelta(days=200, minutes=3))

        output = self._run()

        self.assertIn("near=0, tz_offset=0, date_only=0", output)

    def test_reports_near_duplicate_movie_plays(self):
        movie_item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Film",
            runtime_minutes=120,
        )
        movie = Movie.objects.create(
            user=self.user, item=movie_item, status=Status.COMPLETED.value
        )
        MoviePlay.objects.create(
            movie=movie, end_date=WATCHED, external_id="cinetrack:a:b:1"
        )
        MoviePlay.objects.create(movie=movie, end_date=WATCHED + timedelta(minutes=50))

        output = self._run()

        self.assertIn(
            "Movies: 1 item(s) with 2+ plays; near=1, tz_offset=0, date_only=0", output
        )
        self.assertIn("[near] Film", output)
        self.assertEqual(2, MoviePlay.objects.count())

    def test_unknown_user_reports_nothing(self):
        self.assertIn("No matching users.", self._run("--username", "nobody"))
