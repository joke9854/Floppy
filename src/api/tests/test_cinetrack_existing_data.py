"""Regression matrix for CineTrack bootstrap against pre-existing Floppy data."""

from datetime import UTC, datetime
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch
from uuid import UUID

from django.db import OperationalError

from app.models import TV, Episode, Item, MediaTypes, Movie, MoviePlay, Status

from .base import FloppyApiTestCase
from .test_cinetrack_bootstrap_performance import COMBINED_METADATA


def create_episode_watch_ref():
    """The real writer, captured before a test patches the view's reference."""
    from app.fork_services_episode import create_episode_watch

    return create_episode_watch


class CineTrackExistingDataTests(FloppyApiTestCase):
    """Existing remote state is a supported, non-destructive bootstrap input."""

    MOVIE_EVENT = "cinetrack:existing-data:movie"
    EPISODE_EVENT = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    def _movie_payload(self, media_id="701", *, status=3, watched_at=None, event_id=None):
        entry = {
            "source": "tmdb",
            "media_id": str(media_id),
            "title": f"Movie {media_id}",
            "status": status,
        }
        if watched_at is not None:
            entry["watch"] = {
                "watched_at": watched_at.isoformat().replace("+00:00", "Z"),
                "client_event_id": event_id or self.MOVIE_EVENT,
            }
        return {"movies": [entry]}

    def _ensure_movie(self, payload):
        return self.call_api(
            "post",
            "api_cinetrack_bootstrap_movies_ensure",
            payload=payload,
            headers=self.auth_headers,
        )

    def _show_payload(self, media_id="1002", *, status=1):
        return {
            "shows": [
                {
                    "source": "tmdb",
                    "media_id": str(media_id),
                    "title": f"Show {media_id}",
                    "status": status,
                }
            ]
        }

    def _ensure_show(self, payload):
        return self.call_api(
            "post",
            "api_cinetrack_bootstrap_shows_ensure",
            payload=payload,
            headers=self.auth_headers,
        )

    def _episode_payload(self, watched_at, event_id, *, episode_number=1, season_number=1):
        return {
            "events": [
                {
                    "season_number": season_number,
                    "episode_number": episode_number,
                    "watched_at": watched_at.isoformat().replace("+00:00", "Z"),
                    "client_event_id": str(event_id),
                }
            ]
        }

    def _ensure_episode(self, payload):
        return self.call_api(
            "post",
            "api_media_episode_ensure",
            args=("tv", "tmdb", "1001"),
            payload=payload,
            headers=self.auth_headers,
        )

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_a_existing_item_without_movie_creates_tracking_row_without_metadata(self, metadata):
        movie = self.movie_medias[0]
        item_id = movie.item_id
        movie.delete()
        self.assertTrue(Item.objects.filter(id=item_id).exists())

        response = self._ensure_movie(self._movie_payload(status=2))

        self.assertEqual(response.status_code, HTTP.OK)
        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        imported = Movie.objects.get(user=self.user1, item_id=item_id)
        self.assertEqual(imported.status, Status.PAUSED.value)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_b_existing_movie_with_same_status_is_already_satisfied(self, metadata):
        movie = self.movie_medias[0]
        Movie.objects.filter(pk=movie.pk).update(status=Status.COMPLETED.value)

        response = self._ensure_movie(self._movie_payload(status=3))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(Movie.objects.filter(pk=movie.pk).count(), 1)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_c_legacy_movie_end_date_becomes_exact_historical_play_without_duplicate(self, metadata):
        movie = self.movie_medias[0]
        watched_at = datetime(2024, 1, 3, 21, 13, tzinfo=UTC)
        Movie.objects.filter(pk=movie.pk).update(
            status=Status.COMPLETED.value,
            end_date=watched_at,
        )
        self.assertFalse(MoviePlay.objects.filter(movie=movie).exists())

        response = self._ensure_movie(self._movie_payload(watched_at=watched_at))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        plays = MoviePlay.objects.filter(movie=movie)
        self.assertEqual(plays.count(), 1)
        self.assertEqual(plays.get().end_date, watched_at)
        self.assertEqual(plays.get().external_id, self.MOVIE_EVENT)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_d_legacy_movie_play_adopts_event_id_without_duplicate(self, metadata):
        movie = self.movie_medias[0]
        watched_at = datetime(2024, 1, 8, 19, 40, tzinfo=UTC)
        legacy = MoviePlay.objects.create(movie=movie, end_date=watched_at)

        response = self._ensure_movie(self._movie_payload(watched_at=watched_at))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(MoviePlay.objects.filter(movie=movie).count(), 1)
        legacy.refresh_from_db()
        self.assertEqual(legacy.external_id, self.MOVIE_EVENT)
        self.assertEqual(legacy.end_date, watched_at)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_e_existing_movie_play_with_same_event_id_is_idempotent(self, metadata):
        movie = self.movie_medias[0]
        watched_at = datetime(2024, 2, 14, 22, 1, tzinfo=UTC)
        MoviePlay.objects.create(
            movie=movie,
            end_date=watched_at,
            external_id=self.MOVIE_EVENT,
        )

        response = self._ensure_movie(self._movie_payload(watched_at=watched_at))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(MoviePlay.objects.filter(movie=movie).count(), 1)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_f_legitimate_movie_rewatch_is_preserved_as_separate_play(self, metadata):
        movie = self.movie_medias[0]
        first = datetime(2024, 1, 1, 20, 0, tzinfo=UTC)
        second = datetime(2025, 1, 1, 20, 0, tzinfo=UTC)
        MoviePlay.objects.create(movie=movie, end_date=first, external_id="prior-rewatch")

        response = self._ensure_movie(
            self._movie_payload(watched_at=second, event_id="new-rewatch")
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "created")
        plays = list(MoviePlay.objects.filter(movie=movie).order_by("end_date"))
        self.assertEqual(len(plays), 2)
        self.assertEqual([play.end_date for play in plays], [first, second])
        self.assertEqual({play.external_id for play in plays}, {"prior-rewatch", "new-rewatch"})
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_g_existing_show_item_without_tv_row_is_reused(self, metadata):
        tv = self.tv_medias[1]
        item_id = tv.item_id
        tv.delete()
        self.assertTrue(Item.objects.filter(id=item_id).exists())

        response = self._ensure_show(self._show_payload(status=1))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "created")
        imported = TV.objects.get(user=self.user1, item_id=item_id)
        self.assertEqual(imported.status, Status.IN_PROGRESS.value)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_h_existing_tv_with_desired_status_is_already_satisfied(self, metadata):
        tv = self.tv_medias[1]
        TV.objects.filter(pk=tv.pk).update(status=Status.PAUSED.value)

        response = self._ensure_show(self._show_payload(status=2))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(TV.objects.filter(pk=tv.pk).count(), 1)
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_i_existing_exact_episode_event_is_idempotent_without_metadata(self, metadata):
        episode = self.episode_medias[0]
        watched_at = datetime(2024, 3, 3, 19, 30, tzinfo=UTC)
        Episode.objects.filter(pk=episode.pk).update(
            end_date=watched_at,
            watch_operation_id=self.EPISODE_EVENT,
        )

        response = self._ensure_episode(
            self._episode_payload(watched_at, self.EPISODE_EVENT)
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(Episode.objects.filter(watch_operation_id=self.EPISODE_EVENT).count(), 1)
        metadata.assert_not_called()

    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_j_legacy_episode_exact_timestamp_adopts_event_id_without_duplicate(self, metadata):
        episode = self.episode_medias[0]
        watched_at = datetime(2024, 4, 4, 21, 45, tzinfo=UTC)
        Episode.objects.filter(pk=episode.pk).update(
            end_date=watched_at,
            watch_operation_id=None,
        )

        response = self._ensure_episode(
            self._episode_payload(watched_at, self.EPISODE_EVENT)
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(Episode.objects.filter(watch_operation_id=self.EPISODE_EVENT).count(), 1)
        adopted = Episode.objects.get(pk=episode.pk)
        self.assertEqual(adopted.end_date, watched_at)
        self.assertEqual(adopted.watch_operation_id, self.EPISODE_EVENT)
        # Exact-instant matches are resolved before any provider lookup.
        metadata.assert_not_called()

    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_k_legitimate_episode_rewatch_is_preserved(self, metadata):
        episode = self.episode_medias[0]
        first_id = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
        second_id = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
        first = datetime(2024, 5, 5, 18, 0, tzinfo=UTC)
        second = datetime(2025, 5, 5, 18, 0, tzinfo=UTC)
        Episode.objects.filter(pk=episode.pk).update(
            end_date=first,
            watch_operation_id=first_id,
        )

        response = self._ensure_episode(self._episode_payload(second, second_id))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "created")
        watches = list(
            Episode.objects.filter(
                related_season=episode.related_season,
                item=episode.item,
                end_date__isnull=False,
            ).order_by("end_date")
        )
        self.assertEqual(len(watches), 2)
        self.assertEqual([watch.end_date for watch in watches], [first, second])
        self.assertEqual({watch.watch_operation_id for watch in watches}, {first_id, second_id})
        self.assertEqual(metadata.call_count, 1)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_l_movie_play_from_an_earlier_connection_is_not_duplicated(self, metadata):
        movie = self.movie_medias[0]
        watched_at = datetime(2024, 6, 6, 20, 30, 15, tzinfo=UTC)
        earlier = MoviePlay.objects.create(
            movie=movie,
            end_date=watched_at,
            external_id="cinetrack:old-connection:movie:701:watched:1",
        )

        response = self._ensure_movie(
            self._movie_payload(watched_at=watched_at, event_id="cinetrack:new-connection:movie:701:watched:9"),
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(MoviePlay.objects.filter(movie=movie).count(), 1)
        earlier.refresh_from_db()
        self.assertEqual(earlier.external_id, "cinetrack:old-connection:movie:701:watched:1")
        metadata.assert_not_called()

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_m_episode_from_an_earlier_connection_needs_no_metadata_or_duplicate(self, metadata):
        episode = self.episode_medias[0]
        old_id = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
        watched_at = datetime(2024, 7, 7, 21, 0, 30, tzinfo=UTC)
        Episode.objects.filter(pk=episode.pk).update(end_date=watched_at, watch_operation_id=old_id)

        response = self._ensure_episode(self._episode_payload(watched_at, self.EPISODE_EVENT))

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "already_satisfied")
        self.assertEqual(
            Episode.objects.filter(related_season=episode.related_season, item=episode.item).count(),
            1,
        )
        self.assertEqual(Episode.objects.get(pk=episode.pk).watch_operation_id, old_id)
        metadata.assert_not_called()

    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_o_unknown_episode_is_reported_without_deleting_or_blocking_the_batch(self, metadata):
        episode = self.episode_medias[0]
        kept_at = datetime(2023, 9, 9, 20, 0, tzinfo=UTC)
        Episode.objects.filter(pk=episode.pk).update(end_date=kept_at, watch_operation_id=None)
        before = Episode.objects.count()
        valid_id = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
        unknown_id = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")
        payload = {
            "events": [
                {
                    "season_number": 1,
                    "episode_number": 2,
                    "watched_at": "2024-09-09T20:00:00Z",
                    "client_event_id": str(valid_id),
                },
                {
                    # The fixture season lists episodes 1-3 only.
                    "season_number": 1,
                    "episode_number": 99,
                    "watched_at": "2024-09-10T20:00:00Z",
                    "client_event_id": str(unknown_id),
                },
            ],
        }

        response = self._ensure_episode(payload)

        self.assertEqual(response.status_code, HTTP.OK)
        statuses = {result["client_event_id"]: result["status"] for result in response.json()["results"]}
        self.assertEqual(statuses, {str(valid_id): "created", str(unknown_id): "not_found"})
        self.assertTrue(Episode.objects.filter(watch_operation_id=valid_id).exists())
        self.assertFalse(Episode.objects.filter(watch_operation_id=unknown_id).exists())
        # Nothing pre-existing was deleted.
        self.assertEqual(Episode.objects.count(), before + 1)
        self.assertEqual(Episode.objects.get(pk=episode.pk).end_date, kept_at)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_p_season_without_episode_list_is_reported_per_event(self, metadata):
        metadata.return_value = {key: value for key, value in COMBINED_METADATA.items() if key != "season/1"}
        before = Episode.objects.count()

        response = self._ensure_episode(
            self._episode_payload(datetime(2024, 10, 10, 20, 0, tzinfo=UTC), self.EPISODE_EVENT, episode_number=2),
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "metadata_unavailable")
        self.assertEqual(Episode.objects.count(), before)

    @patch("api.cinetrack_bootstrap_views.time.sleep")
    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_q_locked_database_write_is_retried(self, metadata, sleep):
        real_create = create_episode_watch_ref()
        calls = {"count": 0}

        def locked_once(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise OperationalError("database is locked")
            return real_create(*args, **kwargs)

        with patch("api.cinetrack_bootstrap_views.create_episode_watch", side_effect=locked_once):
            response = self._ensure_episode(
                self._episode_payload(datetime(2024, 11, 11, 20, 0, tzinfo=UTC), self.EPISODE_EVENT, episode_number=2),
            )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "created")
        self.assertEqual(Episode.objects.filter(watch_operation_id=self.EPISODE_EVENT).count(), 1)
        sleep.assert_called_once()

    @patch("api.cinetrack_bootstrap_views.time.sleep")
    @patch(
        "api.cinetrack_bootstrap_views.services.get_media_metadata",
        return_value=COMBINED_METADATA,
    )
    def test_r_persistently_locked_database_answers_busy_and_writes_nothing(self, metadata, sleep):
        before = Episode.objects.count()
        with patch(
            "api.cinetrack_bootstrap_views.create_episode_watch",
            side_effect=OperationalError("database is locked"),
        ):
            response = self._ensure_episode(
                self._episode_payload(datetime(2024, 12, 12, 20, 0, tzinfo=UTC), self.EPISODE_EVENT, episode_number=2),
            )

        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response["Retry-After"], "30")
        self.assertEqual(Episode.objects.count(), before)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_n_specials_season_zero_is_accepted(self, metadata):
        specials = {
            **COMBINED_METADATA["season/1"],
            "season_number": 0,
            "season_title": "Specials",
            "details": {"episodes": 1},
            "episodes": [{"episode_number": 1, "air_date": "2023-01-01", "image": "", "name": "Special"}],
        }
        metadata.return_value = {**COMBINED_METADATA, "season/0": specials}
        watched_at = datetime(2024, 8, 8, 20, 0, tzinfo=UTC)

        response = self._ensure_episode(
            self._episode_payload(watched_at, self.EPISODE_EVENT, season_number=0),
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["results"][0]["status"], "created")
        special = Episode.objects.get(watch_operation_id=self.EPISODE_EVENT)
        self.assertEqual(special.related_season.item.season_number, 0)
        self.assertEqual(special.end_date, watched_at)
