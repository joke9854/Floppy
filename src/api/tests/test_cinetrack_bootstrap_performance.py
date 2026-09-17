"""Focused structural tests for CineTrack Bootstrap V2 performance guarantees."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from app.models import Episode, MediaTypes, Movie, MoviePlay, Status, TV

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
