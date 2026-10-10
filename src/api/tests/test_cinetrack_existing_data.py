"""Regression matrix for CineTrack bootstrap against pre-existing Floppy data."""

from datetime import UTC, datetime
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch
from uuid import UUID

from django.core.cache import cache
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

    def _anime_metadata(self, *, anime=True):
        season_two = {
            **COMBINED_METADATA["season/1"],
            "season_number": 2,
            "season_title": "Season 2",
            "details": {"episodes": 2},
            "episodes": [
                {"episode_number": n, "air_date": f"2023-07-0{n}", "image": "", "name": f"S2 {n}"}
                for n in (1, 2)
            ],
        }
        return {
            **COMBINED_METADATA,
            "genres": ["Animation", "Action & Adventure"] if anime else ["Comedy"],
            "details": {"country": "Japan" if anime else "United States of America", "languages": ["Japanese"] if anime else ["English"]},
            "related": {
                "seasons": [
                    {"season_number": 0, "episode_count": 4},
                    {"season_number": 1, "episode_count": 3},
                    {"season_number": 2, "episode_count": 2},
                ],
            },
            "season/2": season_two,
        }

    def _absolute_payload(self, episode_number, event_id, watched_at):
        return {
            "events": [
                {
                    "season_number": 1,
                    "episode_number": episode_number,
                    "watched_at": watched_at.isoformat().replace("+00:00", "Z"),
                    "client_event_id": str(event_id),
                },
            ],
        }

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_s_anime_absolute_number_is_stored_at_its_tmdb_season(self, metadata):
        metadata.return_value = self._anime_metadata()
        watched_at = datetime(2025, 1, 5, 20, 0, tzinfo=UTC)

        # Season 1 has 3 episodes, so absolute episode 4 is TMDB S02E01.
        response = self._ensure_episode(self._absolute_payload(4, self.EPISODE_EVENT, watched_at))

        self.assertEqual(response.status_code, HTTP.OK)
        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        self.assertEqual((result["stored_season_number"], result["stored_episode_number"]), (2, 1))
        stored = Episode.objects.get(watch_operation_id=self.EPISODE_EVENT)
        self.assertEqual((stored.related_season.item.season_number, stored.item.episode_number), (2, 1))
        self.assertEqual(stored.end_date, watched_at)

        retry = self._ensure_episode(self._absolute_payload(4, self.EPISODE_EVENT, watched_at))

        self.assertEqual(retry.status_code, HTTP.OK)
        retried = retry.json()["results"][0]
        self.assertEqual(retried["status"], "already_satisfied")
        self.assertEqual((retried["stored_season_number"], retried["stored_episode_number"]), (2, 1))
        self.assertEqual(Episode.objects.filter(watch_operation_id=self.EPISODE_EVENT).count(), 1)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_t_non_anime_season_overflow_is_not_translated(self, metadata):
        metadata.return_value = self._anime_metadata(anime=False)
        before = Episode.objects.count()

        response = self._ensure_episode(
            self._absolute_payload(4, self.EPISODE_EVENT, datetime(2025, 2, 5, 20, 0, tzinfo=UTC)),
        )

        self.assertEqual(response.json()["results"][0]["status"], "not_found")
        self.assertNotIn("stored_season_number", response.json()["results"][0])
        self.assertEqual(Episode.objects.count(), before)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_u_anime_number_beyond_all_seasons_is_not_found(self, metadata):
        metadata.return_value = self._anime_metadata()
        before = Episode.objects.count()

        response = self._ensure_episode(
            self._absolute_payload(9, self.EPISODE_EVENT, datetime(2025, 3, 5, 20, 0, tzinfo=UTC)),
        )

        self.assertEqual(response.json()["results"][0]["status"], "not_found")
        self.assertEqual(Episode.objects.count(), before)

    # TMDB merges a two-parter that TVDB (and so Simkl) lists as two episodes:
    # TVDB S02E02+E03 are TMDB S02E02, and TVDB S02E04 is TMDB S02E03.
    TVDB_SEASON_TWO = [
        {"seasonNumber": 2, "number": 1, "name": "Opener", "aired": "2024-01-01"},
        {"seasonNumber": 2, "number": 2, "name": "Two Parter (1)", "aired": "2024-01-08"},
        {"seasonNumber": 2, "number": 3, "name": "Two Parter (2)", "aired": "2024-01-08"},
        {"seasonNumber": 2, "number": 4, "name": "Finale", "aired": "2024-01-15"},
    ]

    def _tvdb(self, default, absolute=()):
        """Fake TVDB episode pages for the default and absolute orders."""
        cache.clear()

        def respond(path, params=None, user=None):
            rows = absolute if "/absolute/" in path else default
            return {"data": {"episodes": list(rows)}, "links": {"next": None}}

        return respond

    def _merged_metadata(self):
        season_two = {
            **COMBINED_METADATA["season/1"],
            "season_number": 2,
            "season_title": "Season 2",
            "details": {"episodes": 3},
            "episodes": [
                {"episode_number": 1, "air_date": "2024-01-01", "image": "", "name": "Opener"},
                {"episode_number": 2, "air_date": "2024-01-08", "image": "", "name": "Two Parter"},
                {"episode_number": 3, "air_date": "2024-01-15", "image": "", "name": "Finale"},
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

    def _season_two_events(self, *events):
        return {
            "events": [
                {
                    "season_number": 2,
                    "episode_number": number,
                    "watched_at": watched_at.isoformat().replace("+00:00", "Z"),
                    "client_event_id": str(event_id),
                }
                for number, watched_at, event_id in events
            ],
        }

    def _stored_at(self, event_id):
        episode = Episode.objects.get(watch_operation_id=event_id)
        return episode.related_season.item.season_number, episode.item.episode_number

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="555")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_v_tvdb_numbered_two_parter_is_stored_at_its_tmdb_episodes(self, metadata, _enabled, _tvdb_id, catalogue):
        metadata.return_value = self._merged_metadata()
        catalogue.side_effect = self._tvdb(self.TVDB_SEASON_TWO)
        second_half = UUID("abababab-abab-4bab-8bab-abababababab")
        finale = UUID("cdcdcdcd-cdcd-4dcd-8dcd-cdcdcdcdcdcd")
        second_at = datetime(2025, 4, 1, 20, 0, tzinfo=UTC)
        finale_at = datetime(2025, 4, 2, 20, 0, tzinfo=UTC)
        payload = self._season_two_events((3, second_at, second_half), (4, finale_at, finale))

        # TVDB S02E04 is unknown to TMDB, which proves season 2 is numbered
        # differently, so S02E03 (which TMDB lists, as another episode) is
        # re-matched by identity instead of being stored one slot off.
        response = self._ensure_episode(payload)

        self.assertEqual(response.status_code, HTTP.OK)
        results = {result["client_event_id"]: result for result in response.json()["results"]}
        self.assertEqual(results[str(second_half)]["status"], "created")
        self.assertEqual((results[str(second_half)]["stored_season_number"], results[str(second_half)]["stored_episode_number"]), (2, 2))
        self.assertEqual(results[str(finale)]["status"], "created")
        self.assertEqual((results[str(finale)]["stored_season_number"], results[str(finale)]["stored_episode_number"]), (2, 3))
        self.assertEqual(self._stored_at(second_half), (2, 2))
        self.assertEqual(self._stored_at(finale), (2, 3))
        self.assertEqual(Episode.objects.get(watch_operation_id=finale).end_date, finale_at)

        retry = self._ensure_episode(payload)

        retried = {result["client_event_id"]: result for result in retry.json()["results"]}
        self.assertEqual({result["status"] for result in retried.values()}, {"already_satisfied"})
        self.assertEqual((retried[str(finale)]["stored_season_number"], retried[str(finale)]["stored_episode_number"]), (2, 3))
        self.assertEqual(Episode.objects.filter(watch_operation_id__in=[second_half, finale]).count(), 2)

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="555")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_w_both_halves_at_one_instant_are_one_watch_and_rewatches_stay_distinct(self, metadata, _enabled, _tvdb_id, catalogue):
        metadata.return_value = self._merged_metadata()
        catalogue.side_effect = self._tvdb(self.TVDB_SEASON_TWO)
        together = datetime(2025, 5, 1, 20, 0, tzinfo=UTC)
        later = datetime(2025, 6, 1, 20, 0, tzinfo=UTC)
        first_half = UUID("12121212-1212-4212-8212-121212121212")
        second_half = UUID("34343434-3434-4434-8434-343434343434")
        rewatch = UUID("56565656-5656-4656-8656-565656565656")
        finale = UUID("78787878-7878-4878-8878-787878787878")

        response = self._ensure_episode(
            self._season_two_events(
                (2, together, first_half), (3, together, second_half), (3, later, rewatch), (4, later, finale),
            ),
        )

        statuses = {result["client_event_id"]: result["status"] for result in response.json()["results"]}
        self.assertEqual(statuses[str(first_half)], "created")
        self.assertEqual(statuses[str(second_half)], "already_satisfied")
        self.assertEqual(statuses[str(rewatch)], "created")
        plays = Episode.objects.filter(
            related_season__item__media_id="1001",
            related_season__item__season_number=2,
            item__episode_number=2,
        )
        self.assertEqual(sorted(plays.values_list("end_date", flat=True)), [together, later])

    @patch("api.cinetrack_bootstrap_views.tvdb._request", side_effect=RuntimeError("TVDB down"))
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="555")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_x_failed_tvdb_lookup_is_retryable_and_writes_nothing(self, metadata, _enabled, _tvdb_id, _catalogue):
        cache.clear()
        metadata.return_value = self._merged_metadata()
        before = Episode.objects.count()

        response = self._ensure_episode(
            self._season_two_events((4, datetime(2025, 7, 1, 20, 0, tzinfo=UTC), self.EPISODE_EVENT)),
        )

        self.assertEqual(response.json()["results"][0]["status"], "metadata_unavailable")
        self.assertEqual(response.json()["results"][0]["reason"], "tvdb_unavailable")
        self.assertEqual(Episode.objects.count(), before)

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="555")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_y_episode_without_a_unique_tmdb_match_is_not_found(self, metadata, _enabled, _tvdb_id, catalogue):
        metadata.return_value = self._merged_metadata()
        catalogue.side_effect = self._tvdb(
            [*self.TVDB_SEASON_TWO, {"seasonNumber": 2, "number": 5, "name": "Unaired Cut", "aired": "2024-03-30"}],
        )
        before = Episode.objects.count()

        response = self._ensure_episode(
            self._season_two_events((5, datetime(2025, 8, 1, 20, 0, tzinfo=UTC), self.EPISODE_EVENT)),
        )

        self.assertEqual(response.json()["results"][0]["status"], "not_found")
        self.assertEqual(response.json()["results"][0]["reason"], "no_unique_tmdb_match")
        # TVDB's title lets the client point the user at it to mark by hand.
        self.assertEqual(response.json()["results"][0]["title"], "Unaired Cut")
        self.assertEqual(Episode.objects.count(), before)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z1_anime_is_detected_with_localized_genre_names(self, metadata):
        # A server with TMDB_LANG=it gets "Animazione" and "Giappone"; spoken
        # languages stay English names.
        localized = self._anime_metadata()
        localized["genres"] = ["Animazione", "Azione & Avventura"]
        localized["details"] = {"country": "Giappone", "languages": ["Japanese"]}
        metadata.return_value = localized

        response = self._ensure_episode(self._absolute_payload(4, self.EPISODE_EVENT, datetime(2025, 9, 1, 20, 0, tzinfo=UTC)))

        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        self.assertEqual((result["stored_season_number"], result["stored_episode_number"]), (2, 1))

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="556")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z2_absolute_number_is_matched_through_tvdb_absolute_order(self, metadata, _enabled, _tvdb_id, catalogue):
        # Not recognised as anime, so only TVDB's absolute order can place it.
        metadata.return_value = self._anime_metadata(anime=False)
        catalogue.side_effect = self._tvdb(
            default=[{"seasonNumber": 1, "number": n, "name": f"Episode {n}", "aired": f"2023-06-0{n}"} for n in (1, 2, 3)],
            absolute=[{"seasonNumber": 1, "number": 4, "absoluteNumber": 4, "name": "S2 1", "aired": "2023-07-01"}],
        )

        response = self._ensure_episode(self._absolute_payload(4, self.EPISODE_EVENT, datetime(2025, 9, 2, 20, 0, tzinfo=UTC)))

        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        self.assertEqual((result["stored_season_number"], result["stored_episode_number"]), (2, 1))

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="557")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z3_season_tmdb_does_not_list_is_matched_not_metadata_unavailable(self, metadata, _enabled, _tvdb_id, catalogue):
        metadata.return_value = self._merged_metadata()
        catalogue.side_effect = self._tvdb([{"seasonNumber": 0, "number": 1, "name": "Finale", "aired": "2024-01-15"}])
        unknown = UUID("9a9a9a9a-9a9a-4a9a-8a9a-9a9a9a9a9a9a")
        payload = {
            "events": [
                {"season_number": 0, "episode_number": 1, "watched_at": "2025-09-03T20:00:00Z", "client_event_id": str(self.EPISODE_EVENT)},
                {"season_number": 0, "episode_number": 2, "watched_at": "2025-09-04T20:00:00Z", "client_event_id": str(unknown)},
            ],
        }

        response = self._ensure_episode(payload)

        results = {result["client_event_id"]: result for result in response.json()["results"]}
        matched = results[str(self.EPISODE_EVENT)]
        self.assertEqual(matched["status"], "created")
        self.assertEqual((matched["stored_season_number"], matched["stored_episode_number"]), (2, 3))
        # A season TMDB never had is a definitive "no counterpart", not a
        # temporary metadata gap that would block the sync forever.
        self.assertEqual(results[str(unknown)]["status"], "not_found")
        self.assertEqual(results[str(unknown)]["reason"], "not_in_tvdb")

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", side_effect=AssertionError("search not needed"))
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z4_tvdb_id_from_tmdb_metadata_and_personal_keys_apply(self, metadata, _enabled, _resolve, catalogue):
        from app.providers import credentials

        seen_users = []

        def fetch(*_args, **_kwargs):
            # Provider calls made for this request must see the caller, so a
            # personal key (the user's own TVDB key) is used.
            seen_users.append(credentials._resolve_user(None))
            return {**self._merged_metadata(), "tvdb_id": "778"}

        metadata.side_effect = fetch
        catalogue.side_effect = self._tvdb(self.TVDB_SEASON_TWO)

        response = self._ensure_episode(
            self._season_two_events((4, datetime(2025, 9, 5, 20, 0, tzinfo=UTC), self.EPISODE_EVENT)),
        )

        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        self.assertEqual((result["stored_season_number"], result["stored_episode_number"]), (2, 3))
        self.assertTrue(seen_users)
        self.assertTrue(all(user is not None and user.pk == self.user1.pk for user in seen_users))
        self.assertTrue(catalogue.call_args.args[0].startswith("series/778/"))

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="559")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z5_double_episode_day_is_paired_by_order_within_the_day(self, metadata, _enabled, _tvdb_id, catalogue):
        # Two episodes aired the same day; TMDB titles are Italian, TVDB's
        # English, so only their order within the day can pair them.
        double_day = self._anime_metadata(anime=False)
        double_day["season/2"] = {
            **double_day["season/2"],
            "episodes": [
                {"episode_number": 1, "air_date": "2023-07-01", "image": "", "name": "Il primo"},
                {"episode_number": 2, "air_date": "2023-07-01", "image": "", "name": "Il secondo"},
            ],
        }
        metadata.return_value = double_day
        catalogue.side_effect = self._tvdb(
            default=[{"seasonNumber": 1, "number": n, "name": f"Episode {n}", "aired": f"2023-06-0{n}"} for n in (1, 2, 3)],
            absolute=[
                {"seasonNumber": 1, "number": 4, "absoluteNumber": 4, "name": "The First", "aired": "2023-07-01"},
                {"seasonNumber": 1, "number": 5, "absoluteNumber": 5, "name": "The Second", "aired": "2023-07-01"},
            ],
        )
        second = UUID("8b8b8b8b-8b8b-4b8b-8b8b-8b8b8b8b8b8b")
        payload = {
            "events": [
                {"season_number": 1, "episode_number": 5, "watched_at": "2025-09-06T21:00:00Z", "client_event_id": str(second)},
                {"season_number": 1, "episode_number": 4, "watched_at": "2025-09-06T20:00:00Z", "client_event_id": str(self.EPISODE_EVENT)},
            ],
        }

        response = self._ensure_episode(payload)

        results = {result["client_event_id"]: result for result in response.json()["results"]}
        self.assertEqual(
            (results[str(self.EPISODE_EVENT)]["stored_season_number"], results[str(self.EPISODE_EVENT)]["stored_episode_number"]),
            (2, 1),
        )
        self.assertEqual((results[str(second)]["stored_season_number"], results[str(second)]["stored_episode_number"]), (2, 2))

    def _absolutely_numbered_metadata(self):
        # Like One Piece on TMDB: season 2 keeps the absolute numbers 4-6.
        season_two = {
            **COMBINED_METADATA["season/1"],
            "season_number": 2,
            "season_title": "Season 2",
            "details": {"episodes": 3},
            "episodes": [
                {"episode_number": 4, "air_date": "2023-07-01", "image": "", "name": "Quattro"},
                {"episode_number": 5, "air_date": "2023-07-08", "image": "", "name": "Cinque"},
                {"episode_number": 6, "air_date": "2023-07-08", "image": "", "name": "Sei"},
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

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="560")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z6_absolutely_numbered_season_is_matched_by_number_not_air_date(self, metadata, _enabled, _tvdb_id, catalogue):
        metadata.return_value = self._absolutely_numbered_metadata()
        # TVDB disagrees on dates: it puts 4 on the day TMDB airs 5 (the Naruto
        # Shippuden 459/460 case) and 5 a week earlier (One Piece 176).
        catalogue.side_effect = self._tvdb(
            default=[{"seasonNumber": 1, "number": n, "name": "", "aired": f"2023-06-0{n}"} for n in (1, 2, 3)],
            absolute=[
                {"seasonNumber": 1, "number": 4, "absoluteNumber": 4, "name": "", "aired": "2023-07-08"},
                {"seasonNumber": 1, "number": 5, "absoluteNumber": 5, "name": "", "aired": "2023-07-01"},
            ],
        )
        fifth = UUID("7c7c7c7c-7c7c-4c7c-8c7c-7c7c7c7c7c7c")
        payload = {
            "events": [
                {"season_number": 1, "episode_number": 4, "watched_at": "2025-09-07T20:00:00Z", "client_event_id": str(self.EPISODE_EVENT)},
                {"season_number": 1, "episode_number": 5, "watched_at": "2025-09-07T21:00:00Z", "client_event_id": str(fifth)},
                {"season_number": 1, "episode_number": 2, "watched_at": "2025-09-07T19:00:00Z", "client_event_id": "6d6d6d6d-6d6d-4d6d-8d6d-6d6d6d6d6d6d"},
            ],
        }

        response = self._ensure_episode(payload)

        results = {result["client_event_id"]: result for result in response.json()["results"]}
        self.assertEqual((results[str(self.EPISODE_EVENT)]["stored_season_number"], results[str(self.EPISODE_EVENT)]["stored_episode_number"]), (2, 4))
        self.assertEqual((results[str(fifth)]["stored_season_number"], results[str(fifth)]["stored_episode_number"]), (2, 5))
        # Season 1 itself is numbered exactly like the tracker: never re-matched.
        self.assertEqual(results["6d6d6d6d-6d6d-4d6d-8d6d-6d6d6d6d6d6d"]["status"], "created")
        self.assertNotIn("stored_season_number", results["6d6d6d6d-6d6d-4d6d-8d6d-6d6d6d6d6d6d"])
        self.assertEqual(self._stored_at(self.EPISODE_EVENT), (2, 4))

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="561")
    @patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True)
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z7_special_title_inside_tmdbs_longer_title_is_matched(self, metadata, _enabled, _tvdb_id, catalogue):
        specials = {
            **COMBINED_METADATA["season/1"],
            "season_number": 0,
            "season_title": "Specials",
            "details": {"episodes": 2},
            "episodes": [
                {"episode_number": 249, "air_date": "2019-05-26", "image": "", "name": "Deleted Scenes from Season 8"},
                {"episode_number": 314, "air_date": "2019-05-26", "image": "", "name": "Game of Thrones: The Last Watch"},
            ],
        }
        metadata.return_value = {
            **COMBINED_METADATA,
            "related": {"seasons": [{"season_number": 0, "episode_count": 2}, {"season_number": 1, "episode_count": 3}]},
            "season/0": specials,
        }
        catalogue.side_effect = self._tvdb([{"seasonNumber": 0, "number": 55, "name": "The Last Watch", "aired": "2019-05-26"}])

        response = self._ensure_episode(
            self._episode_payload(datetime(2025, 9, 8, 20, 0, tzinfo=UTC), self.EPISODE_EVENT, season_number=0, episode_number=55),
        )

        result = response.json()["results"][0]
        self.assertEqual(result["status"], "created")
        self.assertEqual((result["stored_season_number"], result["stored_episode_number"]), (0, 314))

    @patch("api.cinetrack_bootstrap_views.tvdb._request")
    @patch("api.cinetrack_bootstrap_views.tmdb.resolve_tvdb_id_for_tmdb_show", return_value="562")
    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z8_repair_resend_moves_a_two_parter_play_stored_one_off(self, metadata, _tvdb_id, catalogue):
        metadata.return_value = self._merged_metadata()
        catalogue.side_effect = self._tvdb(self.TVDB_SEASON_TWO)
        second_half_at = datetime(2025, 9, 9, 20, 0, tzinfo=UTC)
        finale_at = datetime(2025, 9, 10, 20, 0, tzinfo=UTC)
        old_id = UUID("01010101-0101-4101-8101-010101010101")
        # An older version (no TVDB matching) stored TVDB S02E03 (the second
        # half of the merged two-parter) directly on TMDB S02E03.
        with patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=False):
            self._ensure_episode(self._season_two_events((3, second_half_at, old_id)))
        self.assertEqual(self._stored_at(old_id), (2, 3))

        # The repair re-send uses new event ids, as CineTrack's full re-send does.
        payload = self._season_two_events(
            (3, second_half_at, UUID("02020202-0202-4202-8202-020202020202")),
            (4, finale_at, UUID("03030303-0303-4303-8303-030303030303")),
        )
        payload["repair_coordinates"] = True
        with patch("api.cinetrack_bootstrap_views.tvdb.enabled", return_value=True):
            response = self._ensure_episode(payload)

        self.assertEqual(response.status_code, HTTP.OK)
        # Moved to the merged TMDB episode, keeping its exact time and id.
        moved = Episode.objects.get(watch_operation_id=old_id)
        self.assertEqual((moved.related_season.item.season_number, moved.item.episode_number), (2, 2))
        self.assertEqual(moved.end_date, second_half_at)
        self.assertEqual(self._stored_at(UUID("03030303-0303-4303-8303-030303030303")), (2, 3))
        season_two = Episode.objects.filter(related_season__item__media_id="1001", related_season__item__season_number=2)
        self.assertEqual(season_two.count(), 2)

    @patch("api.cinetrack_bootstrap_views.services.get_media_metadata")
    def test_z9_repair_never_moves_plays_sharing_an_instant(self, metadata):
        metadata.return_value = COMBINED_METADATA
        together = datetime(2025, 9, 11, 20, 0, tzinfo=UTC)
        first = UUID("04040404-0404-4404-8404-040404040404")
        second = UUID("05050505-0505-4505-8505-050505050505")
        self._ensure_episode({"events": [
            {"season_number": 1, "episode_number": 1, "watched_at": "2025-09-11T20:00:00Z", "client_event_id": str(first)},
            {"season_number": 1, "episode_number": 2, "watched_at": "2025-09-11T20:00:00Z", "client_event_id": str(second)},
        ]})

        payload = {
            "events": [
                {"season_number": 1, "episode_number": 3, "watched_at": "2025-09-11T20:00:00Z", "client_event_id": "06060606-0606-4606-8606-060606060606"},
            ],
            "repair_coordinates": True,
        }
        self._ensure_episode(payload)

        # Bulk-marked plays at one instant are never treated as misplaced.
        self.assertEqual(self._stored_at(first), (1, 1))
        self.assertEqual(self._stored_at(second), (1, 2))
        self.assertEqual(Episode.objects.filter(end_date=together).count(), 3)

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
