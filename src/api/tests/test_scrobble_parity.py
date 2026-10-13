"""Scrobble parity: watched threshold, resume on pause, exact time, outcomes.

Drives ``/api/v1/scrobble/`` end to end through the shared webhook processor,
with TMDB metadata stubbed so nothing touches the network.
"""

from datetime import UTC, datetime, timedelta
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from app.models import Item, MediaTypes, Movie, PlaybackProgress, Sources, Status

from .base import FloppyApiTestCase

MOVIE_ID = "900"
EXACT_NOW = datetime(2026, 10, 13, 20, 41, 17, 123456, tzinfo=UTC)


def stub_metadata(test):
    """Patch TMDB lookups the movie processor makes, for one test case."""
    for target, value in (
        ("app.providers.tmdb.movie", {"title": "Parity Movie", "image": ""}),
        ("app.services.metadata_resolution.upsert_provider_links", None),
        ("app.providers.services.get_media_metadata", {"max_progress": None}),
    ):
        patcher = patch(target, return_value=value)
        patcher.start()
        test.addCleanup(patcher.stop)


class ScrobbleParityTestCase(FloppyApiTestCase):
    """Shared helpers: a known movie and a scrobble call."""

    def setUp(self):
        """Seed the movie's metadata Item and stub TMDB."""
        super().setUp()
        stub_metadata(self)
        self.item = Item.objects.create(
            media_id=MOVIE_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Parity Movie",
            runtime_minutes=100,
        )

    def scrobble(self, action, **fields):
        """POST one scrobble event for the movie and return the response."""
        payload = {"action": action, "media_type": "movie", "ids": {"tmdb": MOVIE_ID}}
        payload.update(fields)
        return self.call_api(
            "post",
            "api_scrobble",
            payload=payload,
            headers=self.auth_headers,
        )

    def plays(self):
        """Return the user's completed plays of the movie."""
        return Movie.objects.filter(
            item=self.item,
            user=self.user1,
            status=Status.COMPLETED.value,
        )


class WatchedThresholdTests(ScrobbleParityTestCase):
    """A stop counts as watched at the user's threshold, 80% by default."""

    def test_stop_at_85_percent_is_a_scrobble(self):
        """Past 80% the play is recorded and reported as watched."""
        response = self.scrobble("stop", position_seconds=5100, duration_seconds=6000)

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["detail"], "accepted")
        self.assertEqual(body["action"], "scrobble")
        self.assertEqual(body["progress"], 85.0)
        self.assertIs(body["watched"], True)
        self.assertIs(body["duplicate"], False)
        self.assertEqual(self.plays().count(), 1)

    def test_stop_at_70_percent_only_keeps_the_resume_position(self):
        """Below the threshold nothing is marked watched."""
        response = self.scrobble("stop", position_seconds=4200, duration_seconds=6000)

        body = response.json()
        self.assertEqual(body["action"], "pause")
        self.assertIs(body["watched"], False)
        self.assertIsNone(body["duplicate"])
        self.assertEqual(self.plays().count(), 0)
        progress = PlaybackProgress.objects.get(user=self.user1, item=self.item)
        self.assertEqual(progress.position_seconds, 4200)
        self.assertFalse(progress.completed)

    def test_the_users_threshold_applies(self):
        """A user who set 60% gets 70% counted as watched."""
        self.user1.scrobble_watched_percent = 60
        self.user1.save(update_fields=["scrobble_watched_percent"])

        response = self.scrobble("stop", position_seconds=4200, duration_seconds=6000)

        self.assertIs(response.json()["watched"], True)
        self.assertEqual(self.plays().count(), 1)

    def test_progress_percent_without_a_position(self):
        """A Trakt-style progress value is enough on its own."""
        response = self.scrobble("stop", progress=92.5)

        body = response.json()
        self.assertEqual(body["progress"], 92.5)
        self.assertIs(body["watched"], True)
        self.assertEqual(self.plays().count(), 1)

    def test_explicit_completed_wins_over_progress(self):
        """completed=false keeps a 95% stop unwatched."""
        response = self.scrobble("stop", progress=95, completed=False)

        self.assertIs(response.json()["watched"], False)
        self.assertEqual(self.plays().count(), 0)

    def test_invalid_progress_is_rejected(self):
        """The progress value must be a number from 0 to 100."""
        for value in (150, -1, "90", True):
            with self.subTest(progress=value):
                response = self.scrobble("stop", progress=value)
                self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self.plays().count(), 0)


class PlayTimeAndOutcomeTests(ScrobbleParityTestCase):
    """Exact play time, duplicates and rewatches."""

    def test_play_time_is_the_exact_instant(self):
        """Without played_at the server time is kept to the microsecond."""
        with patch("api.fork_views_scrobble.timezone.now", return_value=EXACT_NOW):
            self.scrobble("stop", progress=100)

        self.assertEqual(self.plays().get().end_date, EXACT_NOW)

    def test_played_at_from_the_client_is_kept(self):
        """An explicit played_at is stored as sent."""
        self.scrobble("stop", progress=100, played_at="2026-10-01T18:30:45.250000Z")

        self.assertEqual(
            self.plays().get().end_date,
            datetime(2026, 10, 1, 18, 30, 45, 250000, tzinfo=UTC),
        )

    def test_the_same_play_sent_twice_is_a_duplicate(self):
        """The second stop is reported as a duplicate and stores nothing."""
        first = self.scrobble("stop", progress=100)
        second = self.scrobble("stop", progress=100)

        self.assertIs(first.json()["duplicate"], False)
        self.assertIs(second.json()["duplicate"], True)
        self.assertIs(second.json()["watched"], True)
        self.assertEqual(self.plays().count(), 1)

    def test_a_rewatch_is_a_new_play(self):
        """A play days after the last one is recorded, not merged."""
        Movie.objects.create(
            item=self.item,
            user=self.user1,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=datetime.now(tz=UTC) - timedelta(days=3),
        )

        response = self.scrobble("stop", progress=100)

        self.assertIs(response.json()["duplicate"], False)
        self.assertEqual(self.plays().count(), 2)


class PauseAndStartTests(ScrobbleParityTestCase):
    """pause saves the resume position; start stores nothing."""

    def test_pause_saves_the_resume_position(self):
        """Pausing at 40% of 100 minutes keeps 2400 seconds."""
        response = self.scrobble("pause", progress=40, duration_seconds=6000)

        body = response.json()
        self.assertEqual(body["action"], "pause")
        self.assertIs(body["watched"], False)
        progress = PlaybackProgress.objects.get(user=self.user1, item=self.item)
        self.assertEqual(progress.position_seconds, 2400)
        self.assertEqual(progress.duration_seconds, 6000)
        self.assertFalse(Movie.objects.filter(user=self.user1, item=self.item).exists())

    def test_pause_updates_the_saved_position(self):
        """A later pause overwrites the earlier position."""
        self.scrobble("pause", position_seconds=600, duration_seconds=6000)
        self.scrobble("pause", position_seconds=1500, duration_seconds=6000)

        progress = PlaybackProgress.objects.get(user=self.user1, item=self.item)
        self.assertEqual(progress.position_seconds, 1500)

    def test_start_stores_nothing(self):
        """A start event only reaches the Now Playing card."""
        response = self.scrobble("start", position_seconds=0, duration_seconds=6000)

        self.assertEqual(response.json()["action"], "start")
        self.assertFalse(PlaybackProgress.objects.filter(user=self.user1).exists())
        self.assertFalse(Movie.objects.filter(user=self.user1, item=self.item).exists())


class ThresholdPreferenceTests(FloppyApiTestCase):
    """The threshold is readable and writable through /user/preferences/."""

    def test_default_is_80(self):
        """New users count 80% as watched."""
        response = self.call_api(
            "get",
            "api_user_preferences",
            headers=self.auth_headers,
        )
        body = response.json()
        self.assertEqual(body["preferences"]["scrobble_watched_percent"], 80)
        self.assertEqual(
            body["choices"]["scrobble_watched_percent"],
            [50, 60, 70, 75, 80, 85, 90, 95],
        )

    def test_patch_sets_an_allowed_value(self):
        """One of the offered percentages is saved."""
        response = self.call_api(
            "patch",
            "api_user_preferences",
            payload={"scrobble_watched_percent": 90},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.scrobble_watched_percent, 90)

    def test_patch_rejects_other_values(self):
        """Values outside the offered choices are refused."""
        response = self.call_api(
            "patch",
            "api_user_preferences",
            payload={"scrobble_watched_percent": 42},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.scrobble_watched_percent, 80)
