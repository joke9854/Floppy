"""Tests for the dedupe_cinetrack_movie_plays repair command."""

from datetime import UTC, datetime, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from app.models import Item, MediaTypes, Movie, MoviePlay, Sources, Status

WATCHED = datetime(2026, 7, 2, 18, 57, 7, tzinfo=UTC)


class DedupeCineTrackMoviePlaysTests(TestCase):
    """Only exact-instant duplicates written by CineTrack are removed."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="watcher", password="12345"
        )
        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Film",
        )
        self.movie = Movie.objects.create(
            user=self.user,
            item=item,
            status=Status.COMPLETED.value,
            end_date=WATCHED,
        )
        self.first = MoviePlay.objects.create(
            movie=self.movie,
            end_date=WATCHED,
            external_id="cinetrack:old:movie:603:watched:1",
        )
        self.duplicate = MoviePlay.objects.create(
            movie=self.movie,
            end_date=WATCHED,
            external_id="cinetrack:new:movie:603:watched:9",
        )

    def _run(self, *args):
        out = StringIO()
        call_command("dedupe_cinetrack_movie_plays", *args, stdout=out)
        return out.getvalue()

    def test_dry_run_reports_and_deletes_nothing(self):
        output = self._run("--username", "watcher")

        self.assertIn("DRY RUN", output)
        self.assertIn("watcher: 1 movie(s), 1 duplicate play(s)", output)
        self.assertIn(f"keep #{self.first.pk}, remove #{self.duplicate.pk}", output)
        self.assertEqual(MoviePlay.objects.count(), 2)

    def test_apply_removes_only_the_exact_instant_cinetrack_duplicate(self):
        other_source = MoviePlay.objects.create(
            movie=self.movie, end_date=WATCHED, external_id="trakt:42"
        )
        rewatch = MoviePlay.objects.create(
            movie=self.movie,
            end_date=WATCHED + timedelta(days=90),
            external_id="cinetrack:new:movie:603:watched:10",
        )

        output = self._run("--apply")

        self.assertIn("Duplicate plays removed: 1", output)
        remaining = set(MoviePlay.objects.values_list("pk", flat=True))
        self.assertEqual(remaining, {self.first.pk, other_source.pk, rewatch.pk})
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.end_date, WATCHED)

    def test_second_apply_finds_nothing(self):
        self._run("--apply")

        output = self._run("--apply")

        self.assertIn("Duplicate plays removed: 0", output)
        self.assertEqual(MoviePlay.objects.count(), 1)
