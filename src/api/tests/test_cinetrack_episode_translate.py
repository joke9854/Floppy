"""Tests for the read-only episode translate endpoint."""

from types import SimpleNamespace
from unittest.mock import patch

from django.core.cache import cache

from app.models import Episode, Item, Season
from app.providers import services

from .base import FloppyApiTestCase

METADATA_PATH = "api.cinetrack_bootstrap_views.services.get_media_metadata"
URL_NAME = "api_media_episode_translate"


def season_metadata(number, episodes):
    """One TMDB season listing."""
    return {
        "media_id": "1001",
        "source": "tmdb",
        "media_type": "season",
        "title": "Show",
        "season_number": number,
        "season_title": f"Season {number}",
        "details": {"episodes": len(episodes)},
        "episodes": [
            {"episode_number": episode, "air_date": f"2020-01-{index + 1:02d}", "image": "", "name": f"E{episode}"}
            for index, episode in enumerate(episodes)
        ],
    }


def metadata_for(seasons, *, listed, languages=()):
    """Return a get_media_metadata stand-in serving only the requested seasons."""
    summary = {
        "media_id": "1001",
        "source": "tmdb",
        "media_type": "tv",
        "title": "Show",
        "details": {"languages": list(languages)},
        "related": {
            "seasons": [{"season_number": number, "episode_count": len(listed[number])} for number in sorted(listed)],
        },
    }

    def fetch(_kind, _media_id, _source, season_numbers):
        return {**summary, **{f"season/{number}": seasons[number] for number in season_numbers if number in seasons}}

    return fetch


def naruto_like():
    """S1 restarts at 1; S4 keeps the absolute numbers 159-220."""
    listed = {1: [1, 2, 3], 4: list(range(159, 221))}
    seasons = {number: season_metadata(number, episodes) for number, episodes in listed.items()}
    return metadata_for(seasons, listed=listed, languages=["Japanese"])


def season_split():
    """Two 26-episode seasons that both restart at 1."""
    listed = {1: list(range(1, 27)), 2: list(range(1, 27))}
    seasons = {number: season_metadata(number, episodes) for number, episodes in listed.items()}
    return metadata_for(seasons, listed=listed, languages=["Japanese"])


class EpisodeTranslateTests(FloppyApiTestCase):
    """Coordinates are translated without ever creating plays."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.counts = self.row_counts()

    @staticmethod
    def row_counts():
        return (Episode.objects.count(), Season.objects.count(), Item.objects.count())

    def translate(self, payload, media_type="tv", headers=True):
        return self.call_api(
            "post",
            URL_NAME,
            args=(media_type, "tmdb", "1001"),
            payload=payload,
            headers=self.auth_headers if headers else None,
        )

    def assert_nothing_written(self):
        self.assertEqual(self.row_counts(), self.counts)

    def test_absolutely_numbered_season_translates(self):
        with patch(METADATA_PATH, side_effect=naruto_like()):
            response = self.translate({"from": "tracker", "episodes": [{"season": 1, "episode": 183}]})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["results"],
            [{
                "season": 1,
                "episode": 183,
                "status": "translated",
                "tmdb": {"season": 4, "episode": 183},
                "absolute": 183,
                "tvdb": None,
                "reason": None,
            }],
        )
        self.assert_nothing_written()

    def test_walked_translation_counts_regular_seasons(self):
        with patch(METADATA_PATH, side_effect=season_split()):
            response = self.translate({"from": "tracker", "episodes": [{"season": 1, "episode": 30}]})

        self.assertEqual(response.status_code, 200)
        result = response.json()["results"][0]
        self.assertEqual(result["status"], "translated")
        self.assertEqual(result["tmdb"], {"season": 2, "episode": 4})
        self.assertEqual(result["absolute"], 30)
        self.assert_nothing_written()

    def test_same_coordinate_and_order_are_kept(self):
        with patch(METADATA_PATH, side_effect=season_split()):
            response = self.translate({
                "from": "tracker",
                "episodes": [
                    {"season": 1, "episode": 2, "watched_at": "2024-01-03T21:13:00Z"},
                    {"season": 2, "episode": 1},
                ],
            })

        results = response.json()["results"]
        self.assertEqual([(r["season"], r["episode"], r["status"]) for r in results], [(1, 2, "same"), (2, 1, "same")])
        self.assertEqual(results[0]["tmdb"], {"season": 1, "episode": 2})
        self.assertEqual([r["absolute"] for r in results], [2, 27])
        self.assert_nothing_written()

    def test_from_tmdb_reports_position_without_translating(self):
        with patch(METADATA_PATH, side_effect=season_split()):
            response = self.translate({
                "from": "tmdb",
                "episodes": [{"season": 2, "episode": 4}, {"season": 1, "episode": 30}],
            })

        found, missing = response.json()["results"]
        self.assertEqual((found["status"], found["tmdb"], found["absolute"]), ("same", {"season": 2, "episode": 4}, 30))
        self.assertEqual((missing["status"], missing["tmdb"], missing["absolute"]), ("not_found", None, None))
        self.assertTrue(missing["reason"])
        self.assert_nothing_written()

    def test_unknown_coordinate_is_not_found(self):
        with patch(METADATA_PATH, side_effect=naruto_like()):
            response = self.translate({"from": "tracker", "episodes": [{"season": 1, "episode": 999}]})

        result = response.json()["results"][0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(result["status"], "not_found")
        self.assertIsNone(result["tmdb"])
        self.assertTrue(result["reason"])
        self.assert_nothing_written()

    def test_unknown_show_is_not_found_for_every_episode(self):
        error = services.ProviderAPIError("tmdb", SimpleNamespace(response=SimpleNamespace(status_code=404)))
        with patch(METADATA_PATH, side_effect=error):
            response = self.translate({
                "from": "tracker",
                "episodes": [{"season": 1, "episode": 1}, {"season": 2, "episode": 3}],
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [(r["status"], r["reason"], r["tmdb"]) for r in response.json()["results"]],
            [("not_found", "unknown_to_provider", None)] * 2,
        )

    def test_provider_failure_is_a_request_error(self):
        error = services.ProviderAPIError("tmdb", SimpleNamespace(response=SimpleNamespace(status_code=500)))
        with patch(METADATA_PATH, side_effect=error):
            response = self.translate({"from": "tracker", "episodes": [{"season": 1, "episode": 1}]})

        self.assertEqual(response.status_code, 404)
        self.assertIn("detail", response.json())

    def test_validation_errors(self):
        episode = {"season": 1, "episode": 1}
        cases = [
            ("tv", {"from": "simkl", "episodes": [episode]}),
            ("tv", {"episodes": [episode]}),
            ("tv", {"from": "tracker", "episodes": []}),
            ("tv", {"from": "tracker", "episodes": [episode] * 401}),
            ("tv", {"from": "tracker", "episodes": [{"season": -1, "episode": 1}]}),
            ("tv", {"from": "tracker", "episodes": [{"season": 1, "episode": 0}]}),
            ("tv", {"from": "tracker", "episodes": [{"season": 1, "episode": 1, "watched_at": "nope"}]}),
            ("movie", {"from": "tracker", "episodes": [episode]}),
        ]
        with patch(METADATA_PATH, side_effect=season_split()) as metadata:
            for media_type, payload in cases:
                with self.subTest(media_type=media_type, payload=str(payload)[:60]):
                    self.assertEqual(self.translate(payload, media_type=media_type).status_code, 400)
            metadata.assert_not_called()

    def test_maximum_batch_is_accepted(self):
        episodes = [{"season": 1, "episode": 1}] * 400
        with patch(METADATA_PATH, side_effect=season_split()):
            response = self.translate({"from": "tracker", "episodes": episodes})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["results"]), 400)

    def test_requires_authentication(self):
        response = self.translate({"from": "tracker", "episodes": [{"season": 1, "episode": 1}]}, headers=False)

        self.assertIn(response.status_code, {401, 403})

    def test_remembered_translation_skips_the_walk(self):
        payload = {"from": "tracker", "episodes": [{"season": 1, "episode": 30}]}
        with patch(METADATA_PATH, side_effect=season_split()) as metadata:
            first = self.translate(payload)
            first_calls = metadata.call_count
            metadata.reset_mock()
            second = self.translate(payload)

        self.assertEqual(first.json(), second.json())
        self.assertEqual(second.json()["results"][0]["tmdb"], {"season": 2, "episode": 4})
        self.assertLess(metadata.call_count, first_calls)
        self.assert_nothing_written()
