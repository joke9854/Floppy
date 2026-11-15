"""FORK (P1-C): people, studios, history genres, ratings graphs and play notes."""

import datetime
from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.core.cache import cache
from django.utils import timezone

from app.models import Item, ItemStudioCredit, MediaTypes, Movie, Sources, Studio
from app.providers import services

from .base import FloppyApiTestCase


def _provider_error(status_code=None):
    if status_code is None:
        return services.ProviderAPIError("tmdb", requests.exceptions.ReadTimeout("x"))
    return services.ProviderAPIError(
        "tmdb", SimpleNamespace(response=SimpleNamespace(status_code=status_code))
    )


class HistoryGenresApiTests(FloppyApiTestCase):
    """GET history/genres/ lists the genres of the caller's tracked items."""

    def test_lists_own_genres_sorted(self):
        item = self.movie_medias[0].item
        item.genres = ["drama", "Action", "123"]
        item.implied_genres = ["Heist"]
        item.save(update_fields=["genres", "implied_genres"])
        other = Item.objects.create(
            media_id="880001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Someone else's",
            genres=["Horror"],
        )
        Movie.objects.create(item=other, user=self.user2)

        response = self.call_api("get", "api_history_genres", headers=self.auth_headers)

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["genres"], ["Action", "drama"])
        self.assertEqual(response.json()["implied_genres"], ["Heist"])


class HistoryNotesApiTests(FloppyApiTestCase):
    """History entries carry the play's notes (the web's watch sessions modal)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        movie = self.movie_medias[0]
        movie.end_date = datetime.datetime(2024, 5, 10, 20, 0, tzinfo=datetime.UTC)
        movie.notes = "Watched with friends"
        movie.save(update_fields=["end_date", "notes"])
        self.item = movie.item

    def _movie_entries(self, **params):
        response = self.call_api(
            "get",
            "api_history",
            params={
                "media_type": "movie",
                "media_id": self.item.media_id,
                "source": self.item.source,
                **params,
            },
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        results = response.json()["results"]
        if params.get("flat"):
            return results
        return [entry for day in results for entry in day["entries"]]

    def test_day_entries_have_notes(self):
        entries = self._movie_entries()
        self.assertEqual(
            [entry["notes"] for entry in entries], ["Watched with friends"]
        )

    def test_flat_entries_have_notes(self):
        entries = self._movie_entries(flat="1")
        self.assertEqual(
            [entry["notes"] for entry in entries], ["Watched with friends"]
        )


class RatingsGraphApiTests(FloppyApiTestCase):
    """GET media/{type}/{source}/{id}/ratings-graph/ returns stored ratings."""

    SHOW_ID = "990001"

    def setUp(self):
        super().setUp()
        cache.clear()
        aired = timezone.now() - datetime.timedelta(days=30)
        Item.objects.create(
            media_id=self.SHOW_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title="Show S1",
            provider_rating=7.9,
            provider_rating_count=40,
        )
        for season, episode, rating, trakt_rating in (
            (0, 1, 6.0, 6.5),
            (1, 1, 8.0, 8.4),
            (1, 2, None, None),
            (2, 1, 9.1, None),
        ):
            Item.objects.create(
                media_id=self.SHOW_ID,
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                season_number=season,
                episode_number=episode,
                title=f"S{season}E{episode}",
                provider_rating=rating,
                provider_rating_count=10 if rating is not None else None,
                trakt_rating=trakt_rating,
                trakt_rating_count=5 if trakt_rating is not None else None,
                release_datetime=aired,
            )

    def _graph(self, **params):
        return self.call_api(
            "get",
            "api_media_ratings_graph",
            args=("tv", Sources.TMDB.value, self.SHOW_ID),
            params=params or None,
            headers=self.auth_headers,
        )

    def test_provider_ratings_by_season_without_specials(self):
        response = self._graph()

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["rating_source"], "provider")
        self.assertFalse(body["pending"])
        self.assertEqual(
            body["seasons"],
            [
                {
                    "season_number": 1,
                    "score": 7.9,
                    "votes": 40,
                    "episodes": [
                        {"episode_number": 1, "score": 8.0, "votes": 10},
                        {"episode_number": 2, "score": None, "votes": 0},
                    ],
                },
                {
                    "season_number": 2,
                    "score": None,
                    "votes": 0,
                    "episodes": [{"episode_number": 1, "score": 9.1, "votes": 10}],
                },
            ],
        )

    def test_single_season_including_specials(self):
        body = self._graph(season="0").json()
        self.assertEqual([season["season_number"] for season in body["seasons"]], [0])

    @patch("app.tasks_trakt.populate_trakt_episode_ratings_for_season.delay")
    @patch("app.providers.trakt.is_configured", return_value=True)
    def test_trakt_pending_queues_each_season_once(self, _configured, delay):
        first = self._graph(rating_source="trakt")
        second = self._graph(rating_source="trakt")

        self.assertTrue(first.json()["pending"])
        self.assertTrue(second.json()["pending"])
        queued = sorted(call.args for call in delay.call_args_list)
        self.assertEqual(
            queued,
            [
                (self.SHOW_ID, Sources.TMDB.value, 1),
                (self.SHOW_ID, Sources.TMDB.value, 2),
            ],
        )

    @patch("app.tasks_trakt.populate_trakt_episode_ratings_for_season.delay")
    @patch("app.providers.trakt.is_configured", return_value=False)
    def test_trakt_not_configured_is_never_pending(self, _configured, delay):
        body = self._graph(rating_source="trakt").json()
        self.assertFalse(body["pending"])
        delay.assert_not_called()

    def test_invalid_requests_are_400(self):
        for params in (
            {"rating_source": "letterboxd"},
            {"season": "-1"},
            {"season": "x"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self._graph(**params).status_code, HTTP.BAD_REQUEST)
        movie = self.call_api(
            "get",
            "api_media_ratings_graph",
            args=("movie", Sources.TMDB.value, "1"),
            headers=self.auth_headers,
        )
        self.assertEqual(movie.status_code, HTTP.BAD_REQUEST)


class PersonApiTests(FloppyApiTestCase):
    """GET people/{source}/{person_id}/ returns the person page data."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.watched = self.movie_medias[0]
        self.watched.end_date = datetime.datetime(
            2024, 5, 10, 20, 0, tzinfo=datetime.UTC
        )
        self.watched.save(update_fields=["end_date"])
        self.watched.item.genres = ["Drama"]
        self.watched.item.save(update_fields=["genres"])

    def _profile(self):
        item = self.watched.item
        return {
            "person_id": "123",
            "source": Sources.TMDB.value,
            "name": "Jane Star",
            "image": "https://example.com/jane.jpg",
            "biography": "Actor.",
            "known_for_department": "Acting",
            "birth_date": "1990-01-01",
            "death_date": None,
            "place_of_birth": "Rome",
            "filmography": [
                {
                    "media_id": item.media_id,
                    "media_type": MediaTypes.MOVIE.value,
                    "title": item.title,
                    "year": 2020,
                    "role": "Lead",
                    "department": "Acting",
                    "credit_type": "cast",
                    "vote_count": 900,
                },
                {
                    "media_id": "770001",
                    "media_type": MediaTypes.TV.value,
                    "title": "Untracked Show",
                    "year": 2018,
                    "role": "Guest",
                    "department": "Acting",
                    "credit_type": "cast",
                    "vote_count": 50,
                },
                {
                    "media_id": "770001",
                    "media_type": MediaTypes.TV.value,
                    "title": "Untracked Show",
                    "department": "Writing",
                    "credit_type": "crew",
                },
            ],
        }

    def _get(self, source=Sources.TMDB.value):
        return self.call_api(
            "get",
            "api_person_detail",
            args=(source, "123"),
            headers=self.auth_headers,
        )

    @patch("app.providers.tmdb.person")
    def test_person_with_credits_and_watched_flags(self, person):
        person.return_value = self._profile()

        response = self._get()

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["person"]["name"], "Jane Star")
        self.assertFalse(body["person"]["is_author"])
        self.assertEqual(
            body["person"]["source_url"], "https://www.themoviedb.org/person/123"
        )
        credits = {credit["media_id"]: credit for credit in body["credits"]}
        self.assertEqual(len(body["credits"]), 2)
        watched = credits[self.watched.item.media_id]
        self.assertTrue(watched["watched"])
        self.assertEqual(watched["item_id"], self.watched.item.id)
        self.assertEqual(watched["genres"], ["Drama"])
        show = credits["770001"]
        self.assertFalse(show["watched"])
        self.assertIsNone(show["item_id"])
        self.assertEqual(show["year"], 2018)
        self.assertEqual(show["departments"], ["Acting", "Writing"])
        self.assertEqual(
            [credit["media_id"] for credit in body["watched_credits"]],
            [self.watched.item.media_id],
        )
        self.assertEqual(body["known_for"][0]["media_id"], self.watched.item.media_id)
        self.assertEqual(body["watched"]["movies"], 1)
        self.assertEqual(body["watched"]["shows"], 0)

    def test_source_without_person_pages_is_400(self):
        response = self._get(source=Sources.IGDB.value)
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(response.json()["code"], "bad_request")

    @patch("app.providers.tmdb.person", side_effect=_provider_error())
    def test_provider_outage_is_503(self, _person):
        response = self._get()
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")
        self.assertEqual(response["Retry-After"], "30")

    @patch("app.providers.tmdb.person", side_effect=_provider_error(404))
    def test_unknown_person_is_404(self, _person):
        response = self._get()
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
        self.assertEqual(response.json()["code"], "not_found")


class StudioApiTests(FloppyApiTestCase):
    """GET studios/{source}/{studio_id}/ returns the studio page data."""

    def setUp(self):
        super().setUp()
        self.studio = Studio.objects.create(
            source=Sources.IGDB.value, source_studio_id="1", name="CD Projekt Red"
        )
        self.game = Item.objects.create(
            media_id="1942",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="The Witcher 3",
            image="https://example.com/w3.jpg",
            release_datetime=datetime.datetime(2015, 5, 19, tzinfo=datetime.UTC),
        )
        ItemStudioCredit.objects.create(item=self.game, studio=self.studio)

    def _get(self, studio_id="1"):
        return self.call_api(
            "get",
            "api_studio_detail",
            args=(Sources.IGDB.value, studio_id),
            headers=self.auth_headers,
        )

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_studio_from_local_credits(self, _profile):
        response = self._get()

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["name"], "CD Projekt Red")
        self.assertEqual(body["description"], "")
        self.assertEqual(
            body["titles"],
            [
                {
                    "media_type": MediaTypes.GAME.value,
                    "source": Sources.IGDB.value,
                    "media_id": "1942",
                    "title": "The Witcher 3",
                    "image": "https://example.com/w3.jpg",
                    "year": 2015,
                    "item_id": self.game.id,
                }
            ],
        )

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_unknown_studio_is_404(self, _profile):
        response = self._get(studio_id="404404")
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
        self.assertEqual(response.json()["code"], "not_found")

    @patch("app.providers.igdb.company_profile", side_effect=_provider_error())
    def test_igdb_outage_is_503(self, _profile):
        response = self._get()
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")
