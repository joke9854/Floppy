"""Batched sync writes: history add/remove, ratings, status, exact watched time."""

import datetime
from decimal import Decimal
from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from api import scopes
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
from app.providers import services
from integrations.models import IntegrationToken

METADATA_TARGET = "api.cinetrack_bootstrap_views.services.get_media_metadata"
FAILING_SHOWS = set()


def season_metadata(media_id):
    return {
        "media_id": media_id,
        "source": "tmdb",
        "media_type": "season",
        "title": f"Show {media_id}",
        "original_title": f"Show {media_id}",
        "localized_title": f"Show {media_id}",
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


def combined_metadata(media_id):
    return {
        "media_id": media_id,
        "source": "tmdb",
        "media_type": "tv",
        "title": f"Show {media_id}",
        "original_title": f"Show {media_id}",
        "localized_title": f"Show {media_id}",
        "image": "https://example.com/tv.jpg",
        "season/1": season_metadata(media_id),
    }


def fake_metadata(media_type, media_id, source, season_numbers=None, **_kwargs):
    if media_id in FAILING_SHOWS:
        raise RuntimeError("provider down")
    return combined_metadata(media_id)


def episode_event(number, watched_at, event_id, media_id="1001", season=1):
    return {
        "source": "tmdb",
        "media_id": media_id,
        "season_number": season,
        "episode_number": number,
        "watched_at": watched_at,
        "client_event_id": event_id,
    }


def movie_event(media_id, watched_at, event_id):
    return {
        "source": "tmdb",
        "media_id": media_id,
        "watched_at": watched_at,
        "client_event_id": event_id,
    }


class SyncWritesBase(APITestCase):
    """Bare users and no pre-tracked media, so counts are exact."""

    def setUp(self):
        super().setUp()
        self.user1 = get_user_model().objects.create_user(username="sync-user1")
        self.user2 = get_user_model().objects.create_user(username="sync-user2")
        self.auth_headers = {"HTTP_X_API_KEY": self.user1.token}
        self.auth_headers2 = {"HTTP_X_API_KEY": self.user2.token}
        releases = patch("app.models.Item.fetch_releases", return_value=None)
        releases.start()
        self.addCleanup(releases.stop)
        FAILING_SHOWS.clear()
        patcher = patch(METADATA_TARGET, side_effect=fake_metadata)
        self.metadata = patcher.start()
        self.addCleanup(patcher.stop)

    def call_api(self, method, name, payload=None, headers=None):
        kwargs = dict(headers or {})
        if payload is not None:
            kwargs.update(data=payload, format="json")
        return getattr(self.client, method)(reverse(name), **kwargs)

    def post(self, name, payload, headers=None):
        return self.call_api(
            "post",
            name,
            payload=payload,
            headers=headers or self.auth_headers,
        )

    def history(self, payload, headers=None):
        return self.post("api_sync_history", payload, headers)

    def remove(self, payload, headers=None):
        return self.post("api_sync_history_remove", payload, headers)

    def outcomes(self, response):
        return [result["outcome"] for result in response.json()["results"]]


class SyncHistoryTests(SyncWritesBase):
    def test_exact_instants_are_stored_and_retry_is_already_satisfied(self):
        payload = {
            "movies": [movie_event("603", "2024-03-01T21:47:18.123456Z", "movie-op-1")],
            "episodes": [
                episode_event(
                    1, "2024-01-03T21:13:00.987654Z", "cinetrack:inst:op-1:1"
                ),
                episode_event(
                    2, "2024-01-08T19:40:00Z", "22222222-2222-4222-8222-222222222222"
                ),
            ],
        }
        first = self.history(payload)
        self.assertEqual(first.status_code, HTTP.OK)
        body = first.json()
        self.assertEqual(self.outcomes(first), ["created"] * 3)
        self.assertEqual(body["counts"], {"created": 3})
        self.assertEqual(
            [(r["type"], r["client_event_id"]) for r in body["results"]],
            [
                ("movie", "movie-op-1"),
                ("episode", "cinetrack:inst:op-1:1"),
                ("episode", "22222222-2222-4222-8222-222222222222"),
            ],
        )
        play = MoviePlay.objects.get()
        self.assertEqual(
            play.end_date,
            datetime.datetime(2024, 3, 1, 21, 47, 18, 123456, tzinfo=datetime.UTC),
        )
        self.assertEqual(Movie.objects.get().status, Status.COMPLETED.value)
        ends = sorted(Episode.objects.values_list("end_date", flat=True))
        self.assertEqual(
            ends,
            [
                datetime.datetime(2024, 1, 3, 21, 13, 0, 987654, tzinfo=datetime.UTC),
                datetime.datetime(2024, 1, 8, 19, 40, 0, tzinfo=datetime.UTC),
            ],
        )

        retry = self.history(payload)
        self.assertEqual(retry.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(retry), ["already_satisfied"] * 3)
        self.assertEqual(retry.json()["counts"], {"already_satisfied": 3})
        self.assertEqual(Episode.objects.count(), 2)
        self.assertEqual(MoviePlay.objects.count(), 1)

    def test_rewatch_with_distinct_ids_and_times_is_two_plays(self):
        response = self.history(
            {
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "rewatch-a"),
                    episode_event(1, "2024-05-03T20:00:00Z", "rewatch-b"),
                ],
                "movies": [
                    movie_event("603", "2024-03-01T21:00:00Z", "movie-a"),
                    movie_event("603", "2024-09-01T21:00:00Z", "movie-b"),
                ],
            }
        )
        self.assertEqual(self.outcomes(response), ["created"] * 4)
        self.assertEqual(Episode.objects.filter(item__episode_number=1).count(), 2)
        self.assertEqual(MoviePlay.objects.count(), 2)
        self.assertEqual(
            Movie.objects.get().end_date,
            datetime.datetime(2024, 9, 1, 21, 0, tzinfo=datetime.UTC),
        )

    def test_same_instant_with_a_different_id_is_adopted(self):
        instant = "2024-01-03T21:13:00.5Z"
        self.history(
            {
                "episodes": [episode_event(1, instant, "first-id")],
                "movies": [movie_event("603", instant, "movie-first")],
            }
        )
        second = self.history(
            {
                "episodes": [episode_event(1, instant, "second-id")],
                "movies": [movie_event("603", instant, "movie-second")],
            }
        )
        self.assertEqual(self.outcomes(second), ["already_satisfied"] * 2)
        self.assertEqual(Episode.objects.count(), 1)
        self.assertEqual(MoviePlay.objects.count(), 1)

    def test_foreign_id_is_a_per_item_conflict_and_the_rest_applies(self):
        self.history(
            {
                "episodes": [episode_event(1, "2024-01-03T21:13:00Z", "bound-id")],
                "movies": [movie_event("603", "2024-03-01T21:00:00Z", "bound-movie")],
            }
        )
        response = self.history(
            {
                "movies": [
                    movie_event("604", "2024-03-02T21:00:00Z", "bound-movie"),
                    movie_event("605", "2024-03-03T21:00:00Z", "fresh-movie"),
                ],
                "episodes": [
                    episode_event(2, "2024-01-04T21:13:00Z", "bound-id"),
                    episode_event(3, "2024-01-05T21:13:00Z", "fresh-id"),
                ],
            }
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            self.outcomes(response), ["conflict", "created", "conflict", "created"]
        )
        self.assertEqual(response.json()["counts"], {"conflict": 2, "created": 2})
        self.assertEqual(Episode.objects.count(), 2)
        self.assertFalse(Movie.objects.filter(item__media_id="604").exists())

    def test_one_show_failing_leaves_the_others_applied(self):
        FAILING_SHOWS.add("2002")
        response = self.history(
            {
                "movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-1")],
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "e-1", media_id="1001"),
                    episode_event(1, "2024-01-04T21:13:00Z", "e-2", media_id="2002"),
                    episode_event(2, "2024-01-05T21:13:00Z", "e-3", media_id="3003"),
                ],
            }
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            self.outcomes(response),
            ["created", "created", "metadata_unavailable", "created"],
        )
        self.assertEqual(
            response.json()["results"][2]["reason"], "provider_unavailable"
        )
        self.assertEqual(Episode.objects.count(), 2)
        self.assertEqual(self.metadata.call_count, 3)

    def test_busy_database_fails_only_that_show_after_backoff(self):
        from django.db import OperationalError

        from api import cinetrack_bootstrap_views as views

        real = views.create_episode_watch

        def locked_for_show_2002(season, item, *args, **kwargs):
            if season.item.media_id == "2002":
                raise OperationalError("database is locked")
            return real(season, item, *args, **kwargs)

        with (
            patch.object(
                views, "create_episode_watch", side_effect=locked_for_show_2002
            ),
            patch.object(views.time, "sleep") as sleep,
        ):
            response = self.history(
                {
                    "episodes": [
                        episode_event(1, "2024-01-03T21:13:00Z", "ok", media_id="1001"),
                        episode_event(
                            1, "2024-01-04T21:13:00Z", "busy", media_id="2002"
                        ),
                    ],
                }
            )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["created", "failed"])
        self.assertEqual(response.json()["results"][1]["reason"], "database_busy")
        self.assertEqual(sleep.call_count, len(views.DB_LOCK_BACKOFF_SECONDS))
        self.assertEqual(Episode.objects.count(), 1)

    def test_known_events_keep_their_outcome_when_the_show_fails(self):
        self.history({"episodes": [episode_event(1, "2024-01-03T21:13:00Z", "known")]})
        FAILING_SHOWS.add("1001")
        response = self.history(
            {
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "known"),
                    episode_event(2, "2024-01-04T21:13:00Z", "new"),
                ],
            }
        )
        self.assertEqual(
            self.outcomes(response), ["already_satisfied", "metadata_unavailable"]
        )

    def test_limits_and_malformed_requests_are_400(self):
        too_many = [
            episode_event(1, "2024-01-03T21:13:00Z", f"id-{n}", media_id="1001")
            for n in range(501)
        ]
        self.assertEqual(
            self.history({"episodes": too_many}).status_code, HTTP.BAD_REQUEST
        )
        many_shows = [
            episode_event(1, "2024-01-03T21:13:00Z", f"id-{n}", media_id=str(5000 + n))
            for n in range(51)
        ]
        self.assertEqual(
            self.history({"episodes": many_shows}).status_code, HTTP.BAD_REQUEST
        )
        self.assertEqual(self.history({}).status_code, HTTP.BAD_REQUEST)
        duplicate = [
            episode_event(1, "2024-01-03T21:13:00Z", "same"),
            episode_event(2, "2024-01-04T21:13:00Z", "same"),
        ]
        self.assertEqual(
            self.history({"episodes": duplicate}).status_code, HTTP.BAD_REQUEST
        )
        cross_type = {
            "movies": [movie_event("603", "2024-03-01T21:00:00Z", "same")],
            "episodes": [episode_event(1, "2024-01-03T21:13:00Z", "same")],
        }
        self.assertEqual(self.history(cross_type).status_code, HTTP.BAD_REQUEST)
        bad_time = {"episodes": [episode_event(1, "2024-01-03", "x")]}
        self.assertEqual(self.history(bad_time).status_code, HTTP.BAD_REQUEST)
        long_id = {"episodes": [episode_event(1, "2024-01-03T21:13:00Z", "x" * 256)]}
        self.assertEqual(self.history(long_id).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(Episode.objects.count(), 0)

    def test_exactly_the_limits_are_accepted(self):
        events = [
            episode_event(1, "2024-01-03T21:13:00Z", f"id-{n}", media_id=str(5000 + n))
            for n in range(50)
        ]
        response = self.history({"episodes": events})
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(len(response.json()["results"]), 50)

    def test_not_found_episode_is_reported_without_blocking_others(self):
        response = self.history(
            {
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "ok"),
                    episode_event(
                        1, "2024-01-04T21:13:00Z", "missing-season", season=9
                    ),
                ],
            }
        )
        self.assertEqual(response.status_code, HTTP.OK)
        results = response.json()["results"]
        self.assertEqual(results[0]["outcome"], "created")
        self.assertIn(results[1]["outcome"], {"not_found", "metadata_unavailable"})
        self.assertIn("reason", results[1])


class SyncHistoryRemoveTests(SyncWritesBase):
    def seed_rewatch(self, headers=None, prefix=""):
        # Episode event ids are unique across users, so a second user needs its own.
        self.history(
            {
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", f"{prefix}play-a"),
                    episode_event(1, "2024-05-03T20:00:00Z", f"{prefix}play-b"),
                    episode_event(2, "2024-01-04T21:13:00Z", f"{prefix}play-c"),
                ],
                "movies": [
                    movie_event("603", "2024-03-01T21:00:00Z", f"{prefix}mplay-a"),
                    movie_event("603", "2024-09-01T21:00:00Z", f"{prefix}mplay-b"),
                ],
            },
            headers,
        )

    @staticmethod
    def ref(**extra):
        return {
            "source": "tmdb",
            "media_id": "1001",
            "season_number": 1,
            "episode_number": 1,
            **extra,
        }

    def test_remove_by_client_event_id_removes_only_that_play(self):
        self.seed_rewatch()
        response = self.remove(
            {
                "episodes": [self.ref(client_event_id="play-a")],
                "movies": [
                    {"source": "tmdb", "media_id": "603", "client_event_id": "mplay-b"}
                ],
            }
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["removed", "removed"])
        self.assertEqual(response.json()["results"][0]["removed_count"], 1)
        remaining = Episode.objects.filter(item__episode_number=1)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(
            remaining.get().end_date,
            datetime.datetime(2024, 5, 3, 20, 0, tzinfo=datetime.UTC),
        )
        movie = Movie.objects.get()
        self.assertEqual(movie.plays.count(), 1)
        self.assertEqual(
            movie.end_date, datetime.datetime(2024, 3, 1, 21, 0, tzinfo=datetime.UTC)
        )

        again = self.remove({"episodes": [self.ref(client_event_id="play-a")]})
        self.assertEqual(self.outcomes(again), ["already_satisfied"])

    def test_remove_by_watched_at_and_all(self):
        self.seed_rewatch()
        response = self.remove(
            {
                "episodes": [
                    self.ref(watched_at="2024-05-03T20:00:00Z"),
                    self.ref(watched_at="2030-01-01T00:00:00Z"),
                    self.ref(episode_number=2, all=True),
                ],
                "movies": [{"source": "tmdb", "media_id": "603", "all": True}],
            }
        )
        self.assertEqual(
            self.outcomes(response),
            ["removed", "removed", "already_satisfied", "removed"],
        )
        self.assertEqual(response.json()["results"][0]["removed_count"], 2)
        self.assertEqual(
            list(Episode.objects.values_list("end_date", flat=True)),
            [datetime.datetime(2024, 1, 3, 21, 13, tzinfo=datetime.UTC)],
        )
        movie = Movie.objects.get()
        self.assertEqual(movie.plays.count(), 0)
        self.assertIsNone(movie.end_date)

    def seed_legacy_movie_watch(self):
        """Seed a movie watched before plays existed: end_date, no play row."""
        self.history(
            {"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-legacy")]},
        )
        movie = Movie.objects.get()
        MoviePlay.objects.filter(movie=movie).delete()
        movie.refresh_from_db()
        self.assertIsNotNone(movie.end_date)
        return movie

    def test_remove_all_clears_a_legacy_watch(self):
        movie = self.seed_legacy_movie_watch()
        response = self.remove(
            {"movies": [{"source": "tmdb", "media_id": "603", "all": True}]},
        )
        self.assertEqual(self.outcomes(response), ["removed"])
        self.assertEqual(response.json()["results"][0]["removed_count"], 1)
        movie.refresh_from_db()
        self.assertIsNone(movie.end_date)

    def test_remove_by_watched_at_clears_only_a_matching_legacy_watch(self):
        movie = self.seed_legacy_movie_watch()
        miss = self.remove(
            {
                "movies": [
                    {
                        "source": "tmdb",
                        "media_id": "603",
                        "watched_at": "2025-01-01T00:00:00Z",
                    },
                ],
            },
        )
        self.assertEqual(self.outcomes(miss), ["already_satisfied"])
        movie.refresh_from_db()
        self.assertIsNotNone(movie.end_date)
        hit = self.remove(
            {
                "movies": [
                    {
                        "source": "tmdb",
                        "media_id": "603",
                        "watched_at": "2024-03-01T21:00:00Z",
                    },
                ],
            },
        )
        self.assertEqual(self.outcomes(hit), ["removed"])
        movie.refresh_from_db()
        self.assertIsNone(movie.end_date)

    def test_remove_all_covers_every_movie_row_of_the_title(self):
        self.history(
            {"movies": [movie_event("603", "2024-03-01T21:00:00Z", "m-first")]},
        )
        repeat = Movie.objects.get()
        repeat.pk = None
        repeat.id = None
        repeat.end_date = datetime.datetime(2024, 9, 1, 21, 0, tzinfo=datetime.UTC)
        repeat.save()
        self.assertEqual(Movie.objects.count(), 2)
        response = self.remove(
            {"movies": [{"source": "tmdb", "media_id": "603", "all": True}]},
        )
        self.assertEqual(self.outcomes(response), ["removed"])
        self.assertEqual(response.json()["results"][0]["removed_count"], 2)
        self.assertEqual(MoviePlay.objects.count(), 0)
        self.assertFalse(Movie.objects.filter(end_date__isnull=False).exists())

    def test_selector_must_be_exactly_one(self):
        self.seed_rewatch()
        for episode in (
            self.ref(),
            self.ref(client_event_id="play-a", watched_at="2024-01-03T21:13:00Z"),
            self.ref(client_event_id="play-a", all=True),
            self.ref(all=False),
        ):
            response = self.remove({"episodes": [episode]})
            self.assertEqual(response.status_code, HTTP.BAD_REQUEST, episode)
        self.assertEqual(
            self.remove(
                {"movies": [{"source": "tmdb", "media_id": "603"}]}
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(self.remove({}).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(Episode.objects.count(), 3)

    def test_nothing_matched_and_untracked_are_already_satisfied(self):
        response = self.remove(
            {
                "episodes": [self.ref(all=True)],
                "movies": [
                    {
                        "source": "tmdb",
                        "media_id": "999",
                        "watched_at": "2024-01-01T00:00:00Z",
                    }
                ],
            }
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["already_satisfied"] * 2)

    def test_id_bound_to_another_episode_or_movie_is_a_conflict(self):
        self.seed_rewatch()
        response = self.remove(
            {
                "episodes": [
                    {
                        "source": "tmdb",
                        "media_id": "7777",
                        "season_number": 1,
                        "episode_number": 1,
                        "client_event_id": "play-a",
                    },
                ],
                "movies": [
                    {"source": "tmdb", "media_id": "604", "client_event_id": "mplay-a"}
                ],
            }
        )
        self.assertEqual(self.outcomes(response), ["conflict", "conflict"])
        self.assertEqual(Episode.objects.count(), 3)
        self.assertEqual(MoviePlay.objects.count(), 2)

    def test_status_after_removal_matches_the_existing_unwatch_operation(self):
        self.seed_rewatch()
        self.seed_rewatch(self.auth_headers2, prefix="u2-")
        for headers in (self.auth_headers, self.auth_headers2):
            self.post(
                "api_sync_status",
                {
                    "shows": [
                        {"source": "tmdb", "media_id": "1001", "status": "completed"}
                    ]
                },
                headers,
            )
        self.remove(
            {
                "episodes": [
                    self.ref(all=True),
                    self.ref(episode_number=2, all=True),
                ],
                "movies": [
                    {"source": "tmdb", "media_id": "603", "client_event_id": "mplay-b"}
                ],
            }
        )
        # The same removals through the model operations the existing routes use.
        season = Season.objects.get(user=self.user2, item__media_id="1001")
        for _ in range(2):
            season.unwatch(1)
        season.unwatch(2)
        Movie.objects.get(user=self.user2).unwatch(external_id="u2-mplay-b")

        def snapshot(user):
            season = Season.objects.get(user=user, item__media_id="1001")
            movie = Movie.objects.get(user=user)
            return (
                season.status,
                TV.objects.get(user=user, item__media_id="1001").status,
                Episode.objects.filter(related_season__user=user).count(),
                movie.end_date,
                movie.status,
                movie.plays.count(),
            )

        self.assertEqual(snapshot(self.user1), snapshot(self.user2))


class SyncRatingsTests(SyncWritesBase):
    def seed(self):
        self.history(
            {
                "movies": [movie_event("603", "2024-03-01T21:00:00Z", "m")],
                "episodes": [
                    episode_event(1, "2024-01-03T21:13:00Z", "e1"),
                    episode_event(1, "2024-02-03T21:13:00Z", "e1b"),
                ],
            }
        )
        self.post(
            "api_sync_status",
            {
                "shows": [
                    {"source": "tmdb", "media_id": "1001", "status": "in_progress"}
                ]
            },
        )

    def test_set_clear_and_idempotence(self):
        self.seed()
        payload = {
            "movies": [{"source": "tmdb", "media_id": "603", "score": 8.5}],
            "shows": [{"source": "tmdb", "media_id": "1001", "score": "7"}],
            "episodes": [
                {
                    "source": "tmdb",
                    "media_id": "1001",
                    "season_number": 1,
                    "episode_number": 1,
                    "score": 9,
                },
            ],
        }
        first = self.post("api_sync_ratings", payload)
        self.assertEqual(first.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(first), ["updated"] * 3)
        self.assertEqual(first.json()["counts"], {"updated": 3})
        self.assertEqual(Movie.objects.get().score, Decimal("8.5"))
        self.assertEqual(TV.objects.get().score, Decimal(7))
        self.assertEqual(
            set(
                Episode.objects.filter(item__episode_number=1).values_list(
                    "score", flat=True
                )
            ),
            {Decimal(9)},
        )

        again = self.post("api_sync_ratings", payload)
        self.assertEqual(self.outcomes(again), ["already_satisfied"] * 3)

        for entries in payload.values():
            entries[0]["score"] = None
        cleared = self.post("api_sync_ratings", payload)
        self.assertEqual(self.outcomes(cleared), ["updated"] * 3)
        self.assertIsNone(Movie.objects.get().score)
        self.assertIsNone(TV.objects.get().score)
        self.assertEqual(
            set(Episode.objects.values_list("score", flat=True)),
            {None},
        )

    def test_untracked_items_are_not_found_and_create_nothing(self):
        response = self.post(
            "api_sync_ratings",
            {
                "movies": [{"source": "tmdb", "media_id": "404", "score": 5}],
                "shows": [{"source": "tmdb", "media_id": "405", "score": 5}],
                "episodes": [
                    {
                        "source": "tmdb",
                        "media_id": "406",
                        "season_number": 1,
                        "episode_number": 1,
                        "score": 5,
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["not_found"] * 3)
        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(TV.objects.count(), 0)
        self.assertEqual(Season.objects.count(), 0)
        self.assertEqual(Episode.objects.count(), 0)

    def test_untracked_episode_of_a_tracked_show_is_not_found(self):
        self.seed()
        response = self.post(
            "api_sync_ratings",
            {
                "episodes": [
                    {
                        "source": "tmdb",
                        "media_id": "1001",
                        "season_number": 1,
                        "episode_number": 3,
                        "score": 5,
                    },
                ],
            },
        )
        self.assertEqual(self.outcomes(response), ["not_found"])

    def test_invalid_scores_and_limits_are_400(self):
        movie = {"source": "tmdb", "media_id": "603"}
        for entry in (
            {**movie, "score": 11},
            {**movie, "score": -1},
            {**movie, "score": "x"},
            {**movie, "score": True},
            movie,
        ):
            self.assertEqual(
                self.post("api_sync_ratings", {"movies": [entry]}).status_code,
                HTTP.BAD_REQUEST,
                entry,
            )
        many = [{**movie, "media_id": str(n), "score": 5} for n in range(501)]
        self.assertEqual(
            self.post("api_sync_ratings", {"movies": many}).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.post("api_sync_ratings", {}).status_code, HTTP.BAD_REQUEST
        )


class SyncStatusTests(SyncWritesBase):
    def test_create_update_and_already_satisfied(self):
        payload = {
            "movies": [
                {
                    "source": "tmdb",
                    "media_id": "603",
                    "status": "planning",
                    "title": "The Matrix",
                }
            ],
            "shows": [{"source": "tmdb", "media_id": "1001", "status": "in_progress"}],
        }
        first = self.post("api_sync_status", payload)
        self.assertEqual(first.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(first), ["created", "created"])
        self.assertEqual(Movie.objects.get().status, Status.PLANNING.value)
        self.assertEqual(Movie.objects.get().item.title, "The Matrix")

        same = self.post("api_sync_status", payload)
        self.assertEqual(self.outcomes(same), ["already_satisfied"] * 2)

        payload["movies"][0]["status"] = "dropped"
        payload["shows"][0]["status"] = "paused"
        changed = self.post("api_sync_status", payload)
        self.assertEqual(self.outcomes(changed), ["updated", "updated"])
        self.assertEqual(Movie.objects.get().status, Status.DROPPED.value)
        self.assertEqual(TV.objects.get().status, Status.PAUSED.value)
        self.assertEqual(changed.json()["counts"], {"updated": 2})

    def test_completed_show_never_creates_episode_history(self):
        response = self.post(
            "api_sync_status",
            {
                "shows": [
                    {"source": "tmdb", "media_id": "1001", "status": "completed"}
                ],
            },
        )
        self.assertEqual(self.outcomes(response), ["created"])
        self.assertEqual(TV.objects.get().status, Status.COMPLETED.value)
        self.assertEqual(Episode.objects.count(), 0)
        self.assertEqual(Season.objects.count(), 0)

        existing = self.post(
            "api_sync_status",
            {
                "shows": [
                    {"source": "tmdb", "media_id": "1001", "status": "in_progress"}
                ],
            },
        )
        self.assertEqual(self.outcomes(existing), ["updated"])
        again = self.post(
            "api_sync_status",
            {
                "shows": [
                    {"source": "tmdb", "media_id": "1001", "status": "completed"}
                ],
            },
        )
        self.assertEqual(self.outcomes(again), ["updated"])
        self.assertEqual(Episode.objects.count(), 0)

    def test_unknown_to_provider_is_not_found(self):
        error = services.ProviderAPIError(
            "tmdb",
            SimpleNamespace(
                response=SimpleNamespace(status_code=404, headers={}, text="")
            ),
        )
        with patch(METADATA_TARGET, side_effect=error):
            response = self.post(
                "api_sync_status",
                {
                    "movies": [
                        {"source": "tmdb", "media_id": "1", "status": "planning"}
                    ],
                    "shows": [
                        {"source": "tmdb", "media_id": "2", "status": "planning"}
                    ],
                },
            )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["not_found", "not_found"])
        self.assertEqual(Item.objects.count(), 0)

    def test_provider_outage_is_failed_not_not_found(self):
        with patch(METADATA_TARGET, side_effect=RuntimeError("down")):
            response = self.post(
                "api_sync_status",
                {
                    "movies": [
                        {"source": "tmdb", "media_id": "1", "status": "planning"}
                    ],
                },
            )
        self.assertEqual(self.outcomes(response), ["failed"])
        self.assertEqual(Movie.objects.count(), 0)

    def test_known_items_need_no_provider_lookup(self):
        Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
        )
        self.metadata.reset_mock()
        with patch(METADATA_TARGET, side_effect=RuntimeError("down")) as lookup:
            response = self.post(
                "api_sync_status",
                {
                    "movies": [
                        {"source": "tmdb", "media_id": "603", "status": "completed"}
                    ],
                },
            )
        self.assertEqual(self.outcomes(response), ["created"])
        lookup.assert_not_called()

    def test_malformed_requests_are_400(self):
        movie = {"source": "tmdb", "media_id": "603", "status": "planning"}
        self.assertEqual(self.post("api_sync_status", {}).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(
            self.post(
                "api_sync_status", {"movies": [{**movie, "status": "watching"}]}
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.post(
                "api_sync_status",
                {"movies": [{"source": "nope", "media_id": "1", "status": "planning"}]},
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        many = [{**movie, "media_id": str(n)} for n in range(201)]
        self.assertEqual(
            self.post("api_sync_status", {"movies": many}).status_code, HTTP.BAD_REQUEST
        )
        self.assertEqual(
            self.post("api_sync_status", {"movies": [movie, movie]}).status_code,
            HTTP.BAD_REQUEST,
        )


class WatchedStateExactTimeTests(SyncWritesBase):
    def setUp(self):
        super().setUp()
        self.item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
        )
        self.url = reverse(
            "api_watched_state",
            kwargs={"media_type": "movie", "source": "tmdb", "media_id": "603"},
        )

    def put(self, payload):
        return self.client.put(
            self.url, data=payload, format="json", **self.auth_headers
        )

    def test_watched_at_is_the_exact_watched_time(self):
        response = self.put(
            {"watched": True, "watched_at": "2025-02-03T04:05:06.789012Z"}
        )
        self.assertEqual(response.status_code, HTTP.OK)
        stored = datetime.datetime.fromisoformat(response.json()["last_watched_at"])
        self.assertEqual(
            stored, datetime.datetime(2025, 2, 3, 4, 5, 6, 789012, tzinfo=datetime.UTC)
        )

    def test_omitted_watched_at_defaults_to_now(self):
        before = timezone.now()
        response = self.put({"watched": True})
        self.assertEqual(response.status_code, HTTP.OK)
        stored = datetime.datetime.fromisoformat(response.json()["last_watched_at"])
        self.assertGreaterEqual(stored, before)
        self.assertLessEqual(stored, timezone.now())

    def test_future_and_malformed_times_are_rejected(self):
        future = (timezone.now() + datetime.timedelta(minutes=30)).isoformat()
        self.assertEqual(
            self.put({"watched": True, "watched_at": future}).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.put({"watched": True, "watched_at": "yesterday"}).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.put({"watched": True, "watched_at": 12345}).status_code,
            HTTP.BAD_REQUEST,
        )

    def test_small_clock_skew_is_tolerated(self):
        soon = (timezone.now() + datetime.timedelta(minutes=2)).isoformat()
        self.assertEqual(
            self.put({"watched": True, "watched_at": soon}).status_code, HTTP.OK
        )


class SyncWritesScopeAndInfoTests(SyncWritesBase):
    ROUTES = (
        "api_sync_history",
        "api_sync_history_remove",
        "api_sync_ratings",
        "api_sync_status",
    )

    def test_tokens_without_watchlist_write_get_403(self):
        _, raw = IntegrationToken.generate(
            user=self.user1,
            name="read only",
            scopes=["watchlist:read", "progress:write"],
        )
        for name in self.ROUTES:
            response = self.post(name, {"movies": []}, {"HTTP_X_API_KEY": raw})
            self.assertEqual(response.status_code, HTTP.FORBIDDEN, name)

    def test_tokens_with_watchlist_write_pass_the_scope_check(self):
        _, raw = IntegrationToken.generate(
            user=self.user1,
            name="writer",
            scopes=["watchlist:write"],
        )
        for name in self.ROUTES:
            response = self.post(name, {}, {"HTTP_X_API_KEY": raw})
            self.assertEqual(response.status_code, HTTP.BAD_REQUEST, name)

    def test_views_are_in_the_scope_map(self):
        for view in (
            "SyncHistoryView",
            "SyncHistoryRemoveView",
            "SyncRatingsView",
            "SyncStatusView",
        ):
            self.assertEqual(
                scopes.VIEW_SCOPES[f"api.fork_views_sync_writes.{view}"],
                {"POST": "watchlist:write"},
            )

    def test_info_advertises_the_extensions(self):
        extensions = self.call_api("get", "api_info").json()["api_extensions"]
        for flag in (
            "sync_history_v1",
            "sync_history_remove_v1",
            "sync_ratings_v1",
            "sync_status_v1",
            "watched_state_exact_time_v1",
        ):
            self.assertIs(extensions[flag], True, flag)
