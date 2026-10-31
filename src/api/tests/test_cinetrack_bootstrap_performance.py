"""Focused structural tests for CineTrack Bootstrap V2 performance guarantees."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.db import connection
from django.test.utils import CaptureQueriesContext

from app.models import (
    TV,
    Episode,
    MediaTypes,
    Movie,
    MoviePlay,
    Status,
    WatchStateSequence,
)

from .base import FloppyApiTestCase

SEASON_METADATA = {
    "media_id": "1001",
    "source": "tmdb",
    "media_type": "season",
    "title": "TV Show 1",
    "original_title": "TV Show 1",
    "localized_title": "TV Show 1",
    "image": "https://example.com/season-1.jpg",
    "season_number": 1,
    "season_title": "Season 1",
    "details": {"episodes": 3},
    "episodes": [
        {
            "episode_number": number,
            "air_date": f"2023-06-0{number}",
            "image": f"https://example.com/s1e{number}.jpg",
            "name": f"Episode {number}",
        }
        for number in (1, 2, 3)
    ],
}
COMBINED_METADATA = {
    "media_id": "1001",
    "source": "tmdb",
    "media_type": "tv",
    "title": "TV Show 1",
    "original_title": "TV Show 1",
    "localized_title": "TV Show 1",
    "image": "https://example.com/tv-1.jpg",
    "season/1": SEASON_METADATA,
}


class CineTrackBootstrapV2PerformanceTests(FloppyApiTestCase):
    """Keep bootstrap request cost proportional to batches, not child rows."""

    def _episode_events(self):
        return [
            {
                "season_number": 1,
                "episode_number": 1,
                "watched_at": "2024-01-03T21:13:00Z",
                "client_event_id": "11111111-1111-4111-8111-111111111111",
            },
            {
                "season_number": 1,
                "episode_number": 2,
                "watched_at": "2024-01-08T19:40:00Z",
                "client_event_id": "22222222-2222-4222-8222-222222222222",
            },
            {
                "season_number": 1,
                "episode_number": 3,
                "watched_at": "2024-02-14T22:01:00Z",
                "client_event_id": "33333333-3333-4333-8333-333333333333",
            },
        ]

    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_episode_batch_fetches_metadata_once_and_retry_fetches_none(self, metadata):
        payload = {"events": self._episode_events()}
        first = self.call_api(
            "post",
            "api_media_episode_ensure",
            args=("tv", "tmdb", "1001"),
            payload=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(first.status_code, HTTP.OK)
        self.assertEqual(metadata.call_count, 1)
        self.assertEqual(metadata.call_args.args[0], "tv_with_seasons")
        self.assertEqual(metadata.call_args.args[3], [1])

        watched = list(
            Episode.objects.filter(
                watch_operation_id__in=[event["client_event_id"] for event in payload["events"]],
            ).order_by("item__episode_number")
        )
        self.assertEqual(len(watched), 3)
        self.assertEqual(
            [episode.end_date.isoformat().replace("+00:00", "Z") for episode in watched],
            [
                "2024-01-03T21:13:00Z",
                "2024-01-08T19:40:00Z",
                "2024-02-14T22:01:00Z",
            ],
        )

        metadata.reset_mock()
        second = self.call_api(
            "post",
            "api_media_episode_ensure",
            args=("tv", "tmdb", "1001"),
            payload=payload,
            headers=self.auth_headers,
        )
        self.assertEqual(second.status_code, HTTP.OK)
        metadata.assert_not_called()
        self.assertEqual(
            [result["status"] for result in second.json()["results"]],
            ["already_satisfied"] * 3,
        )
        self.assertEqual(
            Episode.objects.filter(
                watch_operation_id__in=[event["client_event_id"] for event in payload["events"]],
            ).count(),
            3,
        )

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_movie_batch_avoids_sync_metadata_and_normalizes_status(self, metadata):
        movies = [
            {
                "source": "tmdb",
                "media_id": str(99100 + index),
                "title": f"Imported movie {index}",
                "status": 3,
                "watch": {
                    "watched_at": f"2024-03-{index + 1:02d}T21:47:18Z",
                    "client_event_id": f"cinetrack:movie:{99100 + index}",
                },
            }
            for index in range(10)
        ]
        response = self.call_api(
            "post",
            "api_cinetrack_bootstrap_movies_ensure",
            payload={"movies": movies},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        metadata.assert_not_called()
        imported = Movie.objects.filter(item__media_id__in=[entry["media_id"] for entry in movies])
        self.assertEqual(imported.count(), 10)
        self.assertEqual(set(imported.values_list("status", flat=True)), {Status.COMPLETED.value})
        self.assertEqual(
            MoviePlay.objects.filter(movie__in=imported, external_id__isnull=False).count(),
            10,
        )

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_show_batch_avoids_sync_metadata_and_never_fabricates_episodes(self, metadata):
        shows = [
            {
                "source": "tmdb",
                "media_id": str(99200 + index),
                "title": f"Imported show {index}",
                "status": 3,
            }
            for index in range(10)
        ]
        response = self.call_api(
            "post",
            "api_cinetrack_bootstrap_shows_ensure",
            payload={"shows": shows},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        metadata.assert_not_called()
        imported = TV.objects.filter(item__media_id__in=[entry["media_id"] for entry in shows])
        self.assertEqual(imported.count(), 10)
        self.assertEqual(set(imported.values_list("status", flat=True)), {Status.COMPLETED.value})
        self.assertFalse(
            Episode.objects.filter(
                related_season__related_tv__in=imported,
            ).exists(),
        )

    @patch("app.tasks_metadata_cache.hydrate_cinetrack_bootstrap_items.apply_async")
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_new_items_queue_one_post_commit_hydration_batch(self, metadata, apply_async):
        payload = {
            "movies": [
                {
                    "source": "tmdb",
                    "media_id": "99301",
                    "title": "Hydrate A",
                    "status": 0,
                },
                {
                    "source": "tmdb",
                    "media_id": "99302",
                    "title": "Hydrate B",
                    "status": 0,
                },
            ],
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.call_api(
                "post",
                "api_cinetrack_bootstrap_movies_ensure",
                payload=payload,
                headers=self.auth_headers,
            )
        self.assertEqual(response.status_code, HTTP.OK)
        metadata.assert_not_called()
        apply_async.assert_called_once()
        queued_ids = apply_async.call_args.kwargs["args"][0]
        self.assertEqual(len(queued_ids), 2)

    def test_bootstrap_routes_keep_existing_scope_identity(self):
        from api import cinetrack_bootstrap_views

        self.assertEqual(
            cinetrack_bootstrap_views.CineTrackBootstrapMoviesEnsureView.__module__,
            "api.fork_views_tracking",
        )
        self.assertEqual(
            cinetrack_bootstrap_views.CineTrackBootstrapShowsEnsureView.__module__,
            "api.fork_views_tracking",
        )
        self.assertEqual(
            cinetrack_bootstrap_views.MediaEpisodeEnsureView.__module__,
            "api.fork_views_tracking",
        )


class CineTrackBootstrapQueryGrowthTests(FloppyApiTestCase):
    """Database queries per request must not grow with already-synced rows.

    Re-sending synced history (Retry, resume, reconnect) costs a constant
    number of queries whatever the batch size. New rows cost a bounded number
    each; most of it is Floppy's watch-state upkeep, which runs per saved row
    by design and is deliberately not bypassed.
    """

    # New movies and shows are written and projected in batches, so a larger
    # batch costs no extra queries. Episode events measured 8.4 per new row on
    # 395d7266, with headroom for unrelated model changes.
    NEW_MOVIE_QUERIES = 0
    NEW_SHOW_QUERIES = 0
    NEW_EPISODE_QUERIES = 10

    def _queries(self, name, payload, args=()):
        with CaptureQueriesContext(connection) as context:
            response = self.call_api("post", name, args=args, payload=payload, headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        return len(context.captured_queries)

    @staticmethod
    def _movies(first_id, count):
        return {
            "movies": [
                {
                    "source": "tmdb",
                    "media_id": str(first_id + index),
                    "title": f"Movie {first_id + index}",
                    "status": 3,
                    "watch": {
                        "watched_at": f"2024-03-01T{index % 24:02d}:{index // 24:02d}:00Z",
                        "client_event_id": f"cinetrack:growth:{first_id + index}",
                    },
                }
                for index in range(count)
            ],
        }

    @staticmethod
    def _shows(first_id, count):
        return {
            "shows": [
                {"source": "tmdb", "media_id": str(first_id + index), "title": f"Show {index}", "status": 1}
                for index in range(count)
            ],
        }

    @staticmethod
    def _episode_events(month, count):
        # Rewatches of the fixture's three episodes at distinct instants.
        return {
            "events": [
                {
                    "season_number": 1,
                    "episode_number": index % 3 + 1,
                    "watched_at": f"2024-{month:02d}-01T{index % 24:02d}:{index // 24:02d}:00Z",
                    "client_event_id": f"{month:02d}{index:06d}-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                }
                for index in range(count)
            ],
        }

    def _assert_growth(self, name, small, large, per_new_row, args=()):
        new_small = self._queries(name, small, args)
        new_large = self._queries(name, large, args)
        self.assertLessEqual(new_large - new_small, 15 * per_new_row)
        # The same batches again: everything is already on Floppy.
        self.assertEqual(self._queries(name, large, args), self._queries(name, small, args))

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_movie_queries_are_flat_on_resend_and_bounded_per_new_movie(self, metadata):
        self._assert_growth(
            "api_cinetrack_bootstrap_movies_ensure",
            self._movies(510000, 5),
            self._movies(520000, 20),
            self.NEW_MOVIE_QUERIES,
        )
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_show_queries_are_flat_on_resend_and_bounded_per_new_show(self, metadata):
        self._assert_growth(
            "api_cinetrack_bootstrap_shows_ensure",
            self._shows(530000, 5),
            self._shows(540000, 20),
            self.NEW_SHOW_QUERIES,
        )
        metadata.assert_not_called()

    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_episode_queries_are_flat_on_resend_and_bounded_per_new_event(self, metadata):
        self._assert_growth(
            "api_media_episode_ensure",
            self._episode_events(3, 5),
            self._episode_events(4, 20),
            self.NEW_EPISODE_QUERIES,
            args=("tv", "tmdb", "1001"),
        )
        # One metadata fetch per new batch; resends need none.
        self.assertEqual(metadata.call_count, 2)


class CineTrackBootstrapQueryGrowthWithSyncIndexTests(CineTrackBootstrapQueryGrowthTests):
    """The same checks while an app syncs: the change log and item index run.

    Re-sends stay flat (the index refreshes in batches, not per row). Measured
    per new row on CineTrack-API with the index on and cold caches: movies
    12.7, shows 0, episode events 21.8 (the watched-state change log, which
    records each moved item by design).
    """

    NEW_MOVIE_QUERIES = 14
    NEW_SHOW_QUERIES = 0
    NEW_EPISODE_QUERIES = 24

    def setUp(self):
        super().setUp()
        WatchStateSequence.objects.update_or_create(
            user=self.user1,
            defaults={"emit_changes": True},
        )


class CineTrackMovieEnsureProjectionTests(FloppyApiTestCase):
    """Movies project watch state once, after status and end_date are written."""

    def test_status_only_completion_is_projected(self):
        from app.models import Item
        from app.services.watch_state import effective_state

        item = Item.objects.create(
            source="tmdb", media_id="610001", media_type=MediaTypes.MOVIE.value, title="Planned",
        )
        Movie.objects.create(user=self.user1, item=item, status=Status.PLANNING.value)
        self.assertFalse(effective_state(self.user1, item).watched)

        response = self.call_api(
            "post",
            "api_cinetrack_bootstrap_movies_ensure",
            payload={"movies": [{"source": "tmdb", "media_id": "610001", "title": "Planned", "status": 3}]},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertTrue(effective_state(self.user1, item).watched)

    def test_new_watched_movie_projects_its_play(self):
        from app.services.watch_state import effective_state

        response = self.call_api(
            "post",
            "api_cinetrack_bootstrap_movies_ensure",
            payload={"movies": [{
                "source": "tmdb", "media_id": "610002", "title": "Seen", "status": 3,
                "watch": {"watched_at": "2024-03-01T21:47:18Z", "client_event_id": "cinetrack:movie:610002"},
            }]},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, HTTP.OK)
        movie = Movie.objects.get(user=self.user1, item__media_id="610002")
        state = effective_state(self.user1, movie.item)
        self.assertTrue(state.watched)
        self.assertEqual(state.play_count, 1)
        self.assertEqual(state.last_watched_at.isoformat(), "2024-03-01T21:47:18+00:00")

    def test_batch_projection_matches_per_item_derivation(self):
        from app.models import Item, WatchState
        from app.services.watch_state import derive_state, project_movie_watch_states

        items = [
            Item.objects.create(source="tmdb", media_id=str(620000 + n), media_type=MediaTypes.MOVIE.value, title=f"M{n}")
            for n in range(3)
        ]
        with patch("app.services.watch_state.projection_suspended", return_value=True):
            seen = Movie.objects.create(user=self.user1, item=items[0], status=Status.COMPLETED.value)
            MoviePlay.objects.create(movie=seen, external_id="a", end_date="2024-01-02T10:00:00Z")
            MoviePlay.objects.create(movie=seen, external_id="b", end_date="2024-02-03T10:00:00Z")
            Movie.objects.create(user=self.user1, item=items[1], status=Status.COMPLETED.value)
            Movie.objects.create(user=self.user1, item=items[2], status=Status.PLANNING.value)

        project_movie_watch_states(self.user1, items)

        for item in items:
            expected = derive_state(self.user1, item)
            state = WatchState.objects.get(user=self.user1, item=item)
            self.assertEqual(
                (state.watched, state.play_count, state.first_watched_at, state.last_watched_at),
                (expected.watched, expected.play_count, expected.first_watched_at, expected.last_watched_at),
            )
        with CaptureQueriesContext(connection) as unchanged:
            project_movie_watch_states(self.user1, items)
        self.assertFalse([q for q in unchanged.captured_queries if q["sql"].startswith(("INSERT", "UPDATE"))])


class NewItemBackfillQueueTests(FloppyApiTestCase):
    """Bulk-created items queue the backfills Item's post_save would have queued."""

    def test_queues_runtime_genre_and_credit_backfills_in_one_call_each(self):
        from django.test import override_settings

        from app.models import Item
        from app.signals import queue_backfills_for_new_items

        items = [
            Item(id=1, source="tmdb", media_id="1", media_type=MediaTypes.MOVIE.value),
            Item(id=2, source="tvdb", media_id="2", media_type=MediaTypes.TV.value),
            Item(id=3, source="tmdb", media_id="3", media_type=MediaTypes.EPISODE.value),
        ]
        with (
            override_settings(TESTING=False),
            patch("app.tasks.enqueue_runtime_backfill_items") as runtime,
            patch("app.tasks.enqueue_genre_backfill_items") as genres,
            patch("app.tasks.enqueue_credits_backfill_items") as credits,
        ):
            queue_backfills_for_new_items(items)

        runtime.assert_called_once_with([1, 2])
        genres.assert_called_once_with([1, 2])
        credits.assert_called_once_with([1])
