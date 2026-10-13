"""Read side for main-tracker apps: /sync/items/snapshot/ and /sync/items/changes/."""

import datetime
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from app.models import (
    Episode,
    Item,
    MediaTypes,
    Movie,
    MoviePlay,
    Sources,
    Status,
    SyncItemState,
    WatchStateSequence,
)
from integrations.models import IntegrationToken

from .test_sync_writes import SyncWritesBase, episode_event, movie_event

SNAPSHOT = "api_sync_items_snapshot"
CHANGES = "api_sync_items_changes"


def utc(*args):
    return datetime.datetime(*args, tzinfo=datetime.UTC)


class SyncItemsBase(SyncWritesBase):
    """A user with an active sync connection (changes are recorded)."""

    def setUp(self):
        super().setUp()
        WatchStateSequence.objects.update_or_create(
            user=self.user1,
            defaults={"emit_changes": True},
        )

    def get(self, name, **params):
        from django.urls import reverse

        return self.client.get(reverse(name), params, **self.auth_headers)

    def snapshot_all(self, limit=200):
        """Page through the whole snapshot; return (items, first cursor)."""
        items, after, cursor = [], None, None
        while True:
            params = {"limit": limit}
            if after is not None:
                params["after"] = after
            body = self.get(SNAPSHOT, **params).json()
            cursor = body["cursor"] if cursor is None else cursor
            items += body["results"]
            after = body["next_after"]
            if after is None:
                return items, cursor

    def find(self, items, kind, media_id, season=None, episode=None):
        return next(
            item
            for item in items
            if item["type"] == kind
            and item["media_id"] == media_id
            and item["season_number"] == season
            and item["episode_number"] == episode
        )


class SnapshotTests(SyncItemsBase):
    """The snapshot reads the library directly, exactly."""

    def test_plays_keep_exact_instants_and_rewatches(self):
        """Every play, to the microsecond; a rewatch is a second play."""
        self.history(
            {
                "movies": [
                    movie_event("603", "2024-03-01T21:47:18.123456Z", "m-1"),
                    movie_event("603", "2024-05-02T20:00:00.500000Z", "m-2"),
                ],
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00.987654Z", "e-1"),
                    episode_event(1, "2024-02-03T21:13:00Z", "e-2"),
                ],
            },
        )

        items, _ = self.snapshot_all()

        movie = self.find(items, "movie", "603")
        self.assertEqual(
            [play["watched_at"] for play in movie["plays"]],
            ["2024-03-01T21:47:18.123456+00:00", "2024-05-02T20:00:00.500000+00:00"],
        )
        self.assertEqual(movie["status"], "completed")
        self.assertTrue(movie["in_library"])
        episode = self.find(items, "episode", "1001", 1, 1)
        self.assertEqual(
            [play["watched_at"] for play in episode["plays"]],
            ["2024-01-03T21:13:00.987654+00:00", "2024-02-03T21:13:00+00:00"],
        )
        self.assertIsNone(episode["status"])

    @patch(
        "app.providers.services.get_media_metadata",
        return_value={"max_progress": None},
    )
    def test_a_legacy_movie_row_counts_as_one_play(self, _metadata):
        """A movie row with an end date and no play rows is one play."""
        item = Item.objects.create(
            media_id="604",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Webhook Movie",
        )
        Movie.objects.create(
            item=item,
            user=self.user1,
            status=Status.COMPLETED.value,
            progress=1,
            end_date=utc(2024, 6, 1, 20, 0, 0, 250000),
        )

        items, _ = self.snapshot_all()

        movie = self.find(items, "movie", "604")
        self.assertEqual(len(movie["plays"]), 1)
        self.assertEqual(movie["plays"][0]["watched_at"], "2024-06-01T20:00:00.250000+00:00")

    def test_dropped_episode_rows_are_not_plays(self):
        """The same rule as the episode checkmark."""
        self.history({"episodes": [episode_event(1, "2024-01-03T21:13:00Z", "e-1")]})
        episode = Episode.objects.get()
        episode.dropped = True
        episode.save()

        items, _ = self.snapshot_all()

        self.assertFalse(
            any(item["type"] == "episode" for item in items),
            items,
        )

    def test_show_status_and_score(self):
        """Shows carry their library status."""
        response = self.post(
            "api_sync_status",
            {"shows": [{"source": "tmdb", "media_id": "1001", "status": "planning"}]},
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)

        items, _ = self.snapshot_all()

        show = self.find(items, "show", "1001")
        self.assertEqual(show["status"], "planning")
        self.assertEqual(show["plays"], [])

    def test_paging_covers_everything_once(self):
        """Small pages return every item exactly once."""
        self.history(
            {
                "movies": [
                    movie_event("603", "2024-03-01T21:00:00Z", "m-1"),
                    movie_event("604", "2024-03-02T21:00:00Z", "m-2"),
                    movie_event("605", "2024-03-03T21:00:00Z", "m-3"),
                ],
            },
        )

        items, _ = self.snapshot_all(limit=2)

        self.assertEqual(
            sorted(item["media_id"] for item in items if item["type"] == "movie"),
            ["603", "604", "605"],
        )

    def test_works_without_a_sync_connection(self):
        """The snapshot never depends on the changes index."""
        WatchStateSequence.objects.filter(user=self.user1).update(emit_changes=False)
        self.history({"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]})

        items, cursor = self.snapshot_all()

        self.assertEqual(cursor, 0)
        self.assertEqual([item["media_id"] for item in items], ["603"])
        self.assertFalse(SyncItemState.objects.exists())

    def test_rejects_bad_parameters(self):
        """The limit and after values are validated."""
        self.assertEqual(self.get(SNAPSHOT, limit=0).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self.get(SNAPSHOT, limit=501).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self.get(SNAPSHOT, after=-1).status_code, HTTP.BAD_REQUEST)


class ChangesTests(SyncItemsBase):
    """The feed lists what changed after a cursor."""

    def changes(self, cursor, **params):
        return self.get(CHANGES, cursor=cursor, **params).json()

    def test_a_new_play_appears_after_the_snapshot_cursor(self):
        """Snapshot, then follow the feed from its cursor."""
        self.history({"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]})
        _, cursor = self.snapshot_all()

        self.history({"movies": [movie_event("604", "2024-03-02T21:00:00Z", "m-2")]})
        body = self.changes(cursor)

        self.assertEqual([item["media_id"] for item in body["results"]], ["604"])
        self.assertGreater(body["cursor"], cursor)
        self.assertFalse(body["has_more"])
        self.assertEqual(self.changes(body["cursor"])["results"], [])

    def test_an_unchanged_save_is_not_a_change(self):
        """Saving a row without changing it does not move the item."""
        self.history({"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]})
        cursor = self.changes(0)["cursor"]

        Movie.objects.get(item__media_id="603").save()

        self.assertEqual(self.changes(cursor)["results"], [])

    def test_an_item_that_changes_twice_appears_once(self):
        """Only the latest position of an item is listed."""
        self.history({"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]})
        self.history({"movies": [movie_event("603", "2024-04-01T21:00:00Z", "m-2")]})

        body = self.changes(0)

        self.assertEqual([item["media_id"] for item in body["results"]], ["603"])
        self.assertEqual(len(body["results"][0]["plays"]), 2)

    def test_removing_the_last_play_reports_the_removal(self):
        """An item with nothing left is listed with in_library false."""
        self.history({"episodes": [episode_event(1, "2024-01-03T21:13:00Z", "e-1")]})
        cursor = self.changes(0)["cursor"]

        response = self.remove(
            {
                "episodes": [
                    {
                        "source": "tmdb",
                        "media_id": "1001",
                        "season_number": 1,
                        "episode_number": 1,
                        "all": True,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)

        (episode,) = [
            item for item in self.changes(cursor)["results"] if item["type"] == "episode"
        ]
        self.assertFalse(episode["in_library"])
        self.assertEqual(episode["plays"], [])

    def test_editing_an_older_play_time_is_a_change(self):
        """The watched-state digest misses this; the item index does not."""
        self.history(
            {
                "movies": [
                    movie_event("603", "2024-03-01T21:00:00Z", "m-1"),
                    movie_event("603", "2024-05-01T21:00:00Z", "m-2"),
                ],
            },
        )
        cursor = self.changes(0)["cursor"]

        oldest = MoviePlay.objects.order_by("end_date").first()
        oldest.end_date = utc(2024, 3, 1, 22, 0, 0)
        oldest.save()

        (movie,) = self.changes(cursor)["results"]
        self.assertIn(
            "2024-03-01T22:00:00+00:00",
            [play["watched_at"] for play in movie["plays"]],
        )

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_bootstrap_batches_are_indexed_with_distinct_sequences(self, _metadata):
        """Bulk writes fire no signals; the batched refresh still lists each item."""
        response = self.post(
            "api_cinetrack_bootstrap_movies_ensure",
            {
                "movies": [
                    {
                        "source": "tmdb",
                        "media_id": media_id,
                        "title": f"Movie {media_id}",
                        "status": 3,
                        "watch": {
                            "watched_at": "2024-03-01T21:47:18.123456Z",
                            "client_event_id": f"cinetrack:items:{media_id}",
                        },
                    }
                    for media_id in ("703", "704", "705")
                ],
            },
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)

        results = self.changes(0)["results"]

        movies = {item["media_id"]: item for item in results if item["type"] == "movie"}
        self.assertEqual(sorted(movies), ["703", "704", "705"])
        self.assertEqual(
            movies["703"]["plays"][0]["watched_at"],
            "2024-03-01T21:47:18.123456+00:00",
        )
        sequences = [item["sequence"] for item in results]
        self.assertEqual(len(sequences), len(set(sequences)))

    def test_paging_with_has_more(self):
        """A limit splits the feed; the cursor continues it."""
        self.history(
            {
                "movies": [
                    movie_event("603", "2024-03-01T21:00:00Z", "m-1"),
                    movie_event("604", "2024-03-02T21:00:00Z", "m-2"),
                    movie_event("605", "2024-03-03T21:00:00Z", "m-3"),
                ],
            },
        )

        first = self.changes(0, limit=2)
        second = self.changes(first["cursor"], limit=2)

        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertEqual(
            sorted(
                item["media_id"]
                for item in first["results"] + second["results"]
                if item["type"] == "movie"
            ),
            ["603", "604", "605"],
        )

    def test_nothing_is_indexed_without_a_sync_connection(self):
        """Users who sync nothing pay nothing."""
        WatchStateSequence.objects.filter(user=self.user1).update(emit_changes=False)
        self.history({"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]})

        self.assertEqual(self.changes(0)["results"], [])
        self.assertFalse(SyncItemState.objects.exists())

    def test_users_are_separate(self):
        """Another user's changes never appear."""
        WatchStateSequence.objects.update_or_create(
            user=self.user2,
            defaults={"emit_changes": True},
        )
        self.history(
            {"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")]},
            headers=self.auth_headers2,
        )
        self.assertEqual(self.changes(0)["results"], [])

    def test_needs_sync_read(self):
        """A key without sync:read is refused."""
        _, key = IntegrationToken.generate(
            user=self.user1, name="no sync", scopes=["watchlist:read"]
        )
        from django.urls import reverse

        response = self.client.get(reverse(CHANGES), HTTP_X_API_KEY=key)
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_rejects_bad_parameters(self):
        """The cursor and limit values are validated."""
        self.assertEqual(self.get(CHANGES, cursor=-1).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self.get(CHANGES, cursor="x").status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self.get(CHANGES, limit=0).status_code, HTTP.BAD_REQUEST)
