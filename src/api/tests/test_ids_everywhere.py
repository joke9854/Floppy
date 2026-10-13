"""External ids everywhere: /search/id/ and ``ids`` in the sync write endpoints."""

import datetime
from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

from app.models import Episode, Item, MediaTypes, MoviePlay, Sources
from app.providers.services import ProviderAPIError

from .test_sync_writes import SyncWritesBase, episode_event, movie_event

FIND = "app.providers.tmdb.find"

MATRIX_FIND = {
    "movie_results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-30"}],
    "tv_results": [],
    "tv_episode_results": [],
}
FRIENDS_PILOT_FIND = {
    "movie_results": [],
    "tv_results": [],
    "tv_episode_results": [
        {
            "show_id": 1668,
            "name": "The Pilot",
            "air_date": "1994-09-22",
            "season_number": 1,
            "episode_number": 1,
        },
    ],
}
NOTHING_FOUND = {"movie_results": [], "tv_results": [], "tv_episode_results": []}


def find_by_id(results):
    """Return a find() stub answering from ``{external_id: response}``."""

    def find(external_id, _external_source, language=None):
        return results.get(external_id, NOTHING_FOUND)

    return find


def not_found_error():
    """A ProviderAPIError carrying a 404, as a missing TMDB id raises."""
    response = SimpleNamespace(status_code=404)
    return ProviderAPIError("tmdb", SimpleNamespace(response=response))


class SearchIdTests(SyncWritesBase):
    """GET /api/v1/search/id/."""

    def search(self, **params):
        return self.client.get("/api/v1/search/id/", params, **self.auth_headers)

    def test_imdb_movie_id(self):
        """An IMDb movie id names the TMDB movie."""
        with patch(FIND, side_effect=find_by_id({"tt0133093": MATRIX_FIND})):
            response = self.search(imdb="tt0133093")

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json()["results"],
            [
                {
                    "type": "movie",
                    "source": "tmdb",
                    "media_id": "603",
                    "title": "The Matrix",
                    "year": 1999,
                },
            ],
        )

    def test_imdb_episode_id_names_the_show_and_coordinates(self):
        """An episode's IMDb id returns the show id plus season and episode."""
        with patch(FIND, side_effect=find_by_id({"tt0583459": FRIENDS_PILOT_FIND})):
            response = self.search(imdb="tt0583459")

        (result,) = response.json()["results"]
        self.assertEqual(result["type"], "episode")
        self.assertEqual(result["media_id"], "1668")
        self.assertEqual((result["season_number"], result["episode_number"]), (1, 1))

    def test_known_items_answer_without_the_network(self):
        """An item Floppy already stores is found by its stored IMDb id."""
        Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            provider_external_ids={"imdb_id": "tt0133093"},
        )
        with patch(FIND) as find:
            response = self.search(imdb="tt0133093")

        find.assert_not_called()
        self.assertEqual(response.json()["results"][0]["media_id"], "603")

    def test_type_filters_the_results(self):
        """type=show leaves out movie matches."""
        with patch(FIND, side_effect=find_by_id({"tt0133093": MATRIX_FIND})):
            response = self.search(imdb="tt0133093", type="show")
        self.assertEqual(response.json()["results"], [])

    def test_tmdb_id_needs_a_type(self):
        """TMDB reuses numbers across movies and shows."""
        self.assertEqual(self.search(tmdb="603").status_code, HTTP.BAD_REQUEST)

    def test_tmdb_id_is_checked_against_tmdb(self):
        """An unknown TMDB id is looked up; a missing one returns nothing."""
        with patch(
            "app.providers.tmdb.movie",
            return_value={
                "title": "The Matrix",
                "details": {"release_date": "1999-03-30"},
            },
        ):
            found = self.search(tmdb="603", type="movie")
        self.assertEqual(found.json()["results"][0]["title"], "The Matrix")

        with patch("app.providers.tmdb.movie", side_effect=not_found_error()):
            missing = self.search(tmdb="999999999", type="movie")
        self.assertEqual(missing.status_code, HTTP.OK)
        self.assertEqual(missing.json()["results"], [])

    def test_exactly_one_id_is_required(self):
        """None, or two at once, is a bad request."""
        self.assertEqual(self.search().status_code, HTTP.BAD_REQUEST)
        self.assertEqual(
            self.search(imdb="tt0133093", tvdb="81189").status_code,
            HTTP.BAD_REQUEST,
        )

    def test_provider_failure_is_a_502(self):
        """A TMDB outage is reported, not answered with an empty list."""
        with patch(FIND, side_effect=RuntimeError("tmdb down")):
            response = self.search(imdb="tt0133093")
        self.assertEqual(response.status_code, HTTP.BAD_GATEWAY)

    def test_needs_catalog_read(self):
        """The route is in the scope map like every API view."""
        response = self.client.get("/api/v1/search/id/", {"imdb": "tt0133093"})
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)


class SyncIdsTests(SyncWritesBase):
    """Sync write entries may name items by ids instead of source/media_id."""

    def test_history_accepts_imdb_ids_and_keeps_exact_times(self):
        """A movie and an episode named by IMDb ids are stored like any other."""
        payload = {
            "movies": [
                {
                    "ids": {"imdb": "tt0133093"},
                    "watched_at": "2024-03-01T21:47:18.123456Z",
                    "client_event_id": "movie-ids-1",
                },
            ],
            "episodes": [
                {
                    "ids": {"imdb": "tt0583459"},
                    "season_number": 1,
                    "episode_number": 1,
                    "watched_at": "2024-01-03T21:13:00.987654Z",
                    "client_event_id": "episode-ids-1",
                },
            ],
        }
        finds = {"tt0133093": MATRIX_FIND, "tt0583459": FRIENDS_PILOT_FIND}
        with patch(FIND, side_effect=find_by_id(finds)):
            response = self.history(payload)

        self.assertEqual(response.status_code, HTTP.OK, response.content)
        self.assertEqual(self.outcomes(response), ["created", "created"])
        play = MoviePlay.objects.get()
        self.assertEqual(play.movie.item.media_id, "603")
        self.assertEqual(
            play.end_date,
            datetime.datetime(2024, 3, 1, 21, 47, 18, 123456, tzinfo=datetime.UTC),
        )
        episode = Episode.objects.get()
        self.assertEqual(episode.item.media_id, "1668")
        self.assertEqual(
            episode.end_date,
            datetime.datetime(2024, 1, 3, 21, 13, 0, 987654, tzinfo=datetime.UTC),
        )

    def test_unknown_ids_get_their_own_result_in_place(self):
        """One unknown id does not fail the batch; its slot says not_found."""
        payload = {
            "movies": [
                movie_event("603", "2024-03-01T21:47:18Z", "movie-1"),
                {
                    "ids": {"imdb": "tt0000000"},
                    "watched_at": "2024-03-02T21:00:00Z",
                    "client_event_id": "movie-unknown",
                },
            ],
            "episodes": [
                episode_event(1, "2024-01-03T21:13:00Z", "episode-1"),
            ],
        }
        with patch(FIND, side_effect=find_by_id({})):
            response = self.history(payload)

        body = response.json()
        self.assertEqual(
            [(r["client_event_id"], r["outcome"]) for r in body["results"]],
            [
                ("movie-1", "created"),
                ("movie-unknown", "not_found"),
                ("episode-1", "created"),
            ],
        )
        self.assertEqual(body["results"][1]["reason"], "unknown_ids")
        self.assertEqual(body["results"][1]["ids"], {"imdb": "tt0000000"})
        self.assertEqual(body["counts"], {"created": 2, "not_found": 1})

    def test_a_batch_of_only_unknown_ids_is_answered(self):
        """Nothing resolvable still returns 200 with a result per entry."""
        payload = {
            "movies": [
                {
                    "ids": {"imdb": "tt0000000"},
                    "watched_at": "2024-03-02T21:00:00Z",
                    "client_event_id": "movie-unknown",
                },
            ],
        }
        with patch(FIND, side_effect=find_by_id({})):
            response = self.history(payload)

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(self.outcomes(response), ["not_found"])
        self.assertFalse(MoviePlay.objects.exists())

    def test_provider_outage_is_metadata_unavailable(self):
        """A lookup that cannot reach TMDB is not reported as unknown."""
        payload = {
            "movies": [
                {
                    "ids": {"imdb": "tt0133093"},
                    "watched_at": "2024-03-02T21:00:00Z",
                    "client_event_id": "movie-outage",
                },
            ],
        }
        with patch(FIND, side_effect=RuntimeError("tmdb down")):
            response = self.history(payload)

        (result,) = response.json()["results"]
        self.assertEqual(result["outcome"], "metadata_unavailable")
        self.assertEqual(result["reason"], "provider_unavailable")

    def test_tmdb_id_in_ids_needs_no_lookup(self):
        """ids.tmdb is used as is."""
        payload = {
            "movies": [
                {
                    "ids": {"tmdb": "603"},
                    "watched_at": "2024-03-01T21:47:18Z",
                    "client_event_id": "movie-tmdb-ids",
                },
            ],
        }
        with patch(FIND) as find:
            response = self.history(payload)
        find.assert_not_called()
        self.assertEqual(self.outcomes(response), ["created"])

    def test_status_and_ratings_accept_ids(self):
        """The item endpoints resolve ids the same way."""
        with patch(FIND, side_effect=find_by_id({"tt0133093": MATRIX_FIND})):
            status = self.post(
                "api_sync_status",
                {"movies": [{"ids": {"imdb": "tt0133093"}, "status": "planning"}]},
            )
            rating = self.post(
                "api_sync_ratings",
                {
                    "movies": [
                        {"ids": {"imdb": "tt0133093"}, "score": 8.5},
                        {"ids": {"imdb": "tt0000000"}, "score": 7},
                    ],
                },
            )

        self.assertEqual(status.status_code, HTTP.OK, status.content)
        (status_result,) = status.json()["results"]
        self.assertEqual(status_result["media_id"], "603")
        self.assertIn(status_result["outcome"], {"created", "updated"})
        results = rating.json()["results"]
        self.assertEqual(results[0]["media_id"], "603")
        self.assertEqual(results[1]["outcome"], "not_found")
        self.assertEqual(results[1]["ids"], {"imdb": "tt0000000"})

    def test_source_and_media_id_still_win(self):
        """An entry with source/media_id is never re-resolved from ids."""
        payload = {
            "movies": [
                {
                    **movie_event("603", "2024-03-01T21:47:18Z", "movie-both"),
                    "ids": {"imdb": "tt9999999"},
                },
            ],
        }
        with patch(FIND) as find:
            response = self.history(payload)
        find.assert_not_called()
        self.assertEqual(self.outcomes(response), ["created"])
