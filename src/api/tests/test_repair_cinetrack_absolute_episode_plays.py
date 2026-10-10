"""Tests for the repair_cinetrack_absolute_episode_plays command."""

from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch
from uuid import UUID

from django.core.management import call_command

from app.models import Episode

from .base import FloppyApiTestCase
from .test_cinetrack_bootstrap_performance import COMBINED_METADATA

FIRST = datetime(2025, 5, 12, 20, 0, tzinfo=UTC)
SECOND = datetime(2025, 5, 13, 20, 0, tzinfo=UTC)
MISPLACED = UUID("45945945-9459-4459-8459-459459459459")
OWN = UUID("46046046-0460-4460-8460-460460460460")


def absolutely_numbered_metadata():
    """Season 2 keeps absolute numbers 4-6, like Naruto Shippuden on TMDB."""
    season_two = {
        **COMBINED_METADATA["season/1"],
        "season_number": 2,
        "season_title": "Season 2",
        "details": {"episodes": 3},
        "episodes": [
            {"episode_number": number, "air_date": "2023-07-01", "image": "", "name": f"E{number}"}
            for number in (4, 5, 6)
        ],
    }
    return {
        **COMBINED_METADATA,
        "related": {
            "seasons": [
                {"season_number": 1, "episode_count": 3},
                {"season_number": 2, "episode_count": 3},
            ],
        },
        "season/2": season_two,
    }


@patch(
    "app.management.commands.repair_cinetrack_absolute_episode_plays.services.get_media_metadata",
    side_effect=lambda *_args, **_kwargs: absolutely_numbered_metadata(),
)
class RepairCineTrackAbsoluteEpisodePlaysTests(FloppyApiTestCase):
    """Only the misplacement shape is moved, and only with --apply."""

    def setUp(self):
        super().setUp()
        events = [
            # 459's watch stored on 460 by the old air-date match, next to 460's own.
            (5, FIRST, MISPLACED),
            (5, SECOND, OWN),
            (6, datetime(2025, 5, 14, 20, 0, tzinfo=UTC), UUID("46146146-1461-4461-8461-461461461461")),
        ]
        with patch(
            "api.cinetrack_bootstrap_views.services.get_media_metadata",
            return_value=absolutely_numbered_metadata(),
        ):
            response = self.call_api(
                "post",
                "api_media_episode_ensure",
                args=("tv", "tmdb", "1001"),
                payload={
                    "events": [
                        {
                            "season_number": 2,
                            "episode_number": number,
                            "watched_at": watched_at.isoformat().replace("+00:00", "Z"),
                            "client_event_id": str(event_id),
                        }
                        for number, watched_at, event_id in events
                    ],
                },
                headers=self.auth_headers,
            )
        self.assertEqual(response.status_code, 200)

    def _run(self, *args):
        out = StringIO()
        call_command("repair_cinetrack_absolute_episode_plays", "--username", self.user1.username, *args, stdout=out)
        return out.getvalue()

    def _episode_of(self, operation_id):
        return Episode.objects.select_related("item").get(watch_operation_id=operation_id).item.episode_number

    def test_dry_run_lists_the_earliest_play_and_changes_nothing(self, _metadata):
        output = self._run()

        self.assertIn("E5 -> E4", output)
        self.assertIn("Plays would be moved: 1", output)
        self.assertEqual(self._episode_of(MISPLACED), 5)

    def test_apply_moves_it_with_its_exact_time_and_operation_id(self, _metadata):
        self._run("--apply")

        moved = Episode.objects.select_related("item").get(watch_operation_id=MISPLACED)
        self.assertEqual(moved.item.episode_number, 4)
        self.assertEqual(moved.end_date, FIRST)
        self.assertEqual(self._episode_of(OWN), 5)
        self.assertIn("Plays would be moved: 0", self._run())

    def test_no_move_when_the_neighbour_already_has_a_play(self, _metadata):
        self._run("--apply")
        before = list(Episode.objects.order_by("id").values_list("id", "item_id", "end_date"))

        self._run("--apply")

        self.assertEqual(list(Episode.objects.order_by("id").values_list("id", "item_id", "end_date")), before)
