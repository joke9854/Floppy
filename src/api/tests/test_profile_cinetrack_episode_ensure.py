"""The CineTrack episode re-send profiler reports timings and changes nothing."""

from io import StringIO

from django.core.management import call_command

from app.models import Episode

from .test_sync_writes import SyncWritesBase, episode_event


class ProfileCommandTests(SyncWritesBase):
    """Run the profiler against a user's stored plays."""

    def setUp(self):
        super().setUp()
        self.history(
            {
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "e-1"),
                    episode_event(2, "2024-01-04T21:13:00Z", "e-2"),
                ],
            },
        )
        self.before = list(Episode.objects.values_list("id", "end_date", "watch_operation_id").order_by("id"))

    def profile(self, *args):
        out = StringIO()
        call_command(
            "profile_cinetrack_episode_ensure",
            "--user",
            self.user1.username,
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_a_replay_takes_the_fast_path_and_changes_nothing(self):
        """Stored plays match by exact instant: no lookup, nothing written."""
        output = self.profile("--show", "1001")

        self.assertIn("show 1001: events=2", output)
        self.assertIn("unresolved=0", output)
        self.assertIn("already_satisfied=2", output)
        self.assertNotIn("metadata_ms", output)
        self.assertEqual(
            list(Episode.objects.values_list("id", "end_date", "watch_operation_id").order_by("id")),
            self.before,
        )

    def test_force_lookup_takes_the_slow_path_and_changes_nothing(self):
        """One unmatchable episode makes the request fetch metadata."""
        output = self.profile("--show", "1001", "--force-lookup")

        self.assertIn("unresolved=1", output)
        self.assertIn("metadata_ms=", output)
        self.assertEqual(
            list(Episode.objects.values_list("id", "end_date", "watch_operation_id").order_by("id")),
            self.before,
        )

    def test_without_show_it_picks_the_shows_with_most_plays(self):
        """The default profiles the user's biggest shows."""
        self.assertIn("show 1001:", self.profile("--shows", "1"))
