"""The web episode page API (v2 P4-C3) against the Django episode page."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

import events.tasks  # signal handlers reach events.tasks lazily
from app.models import MediaTypes, Sources
from users.models import ThemeChoices

SHOW = {
    "title": "Test TV Show",
    "media_id": "1668",
    "source": Sources.TMDB.value,
    "media_type": MediaTypes.TV.value,
    "image": "http://example.com/image.jpg",
    "season/1": {
        "title": "Season 1",
        "season_title": "Season 1",
        "media_id": "1668",
        "media_type": MediaTypes.SEASON.value,
        "source": Sources.TMDB.value,
        "image": "http://example.com/season.jpg",
        "episodes": [{"episode_number": number} for number in range(1, 4)],
    },
}
EPISODES = [
    {
        "media_id": "1668",
        "source": Sources.TMDB.value,
        "media_type": MediaTypes.EPISODE.value,
        "season_number": 1,
        "episode_number": number,
        "title": f"Episode {number}",
        "air_date": f"2023-01-{number:02d}",
        "overview": f"Overview {number}.",
        "watched": False,
    }
    for number in range(1, 4)
]
EPISODE_METADATA = {
    "score": 8.2,
    "score_count": 120,
    "cast": [{"person_id": "5", "name": "Guest Person", "role": "Waiter"}],
    "crew": [{"person_id": "6", "name": "Some Director", "role": "Director"}],
}


@patch("app.views.tmdb.episode", return_value=EPISODE_METADATA)
@patch("app.providers.services.get_media_metadata", side_effect=lambda *_a, **_k: SHOW)
@patch("app.providers.tmdb.process_episodes", return_value=EPISODES)
class EpisodeScreenApiTests(TestCase):
    """GET /api/v1/details/episode/... says what the page renders."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="episode", password="x")
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self.client.force_login(self.user)

    def _page(self, number):
        return self.client.get(
            reverse(
                "episode_details",
                kwargs={
                    "source": "tmdb",
                    "media_id": "1668",
                    "title": "test-tv-show",
                    "season_number": 1,
                    "episode_number": number,
                },
            )
        )

    def _api(self, number):
        response = self.client.get(
            reverse("api_episode_screen", args=["tmdb", "1668", 1, number])
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_episode_page(self, *_mocks):
        body = self._api(2)
        page = self._page(2)

        self.assertEqual(body["title"], page.context["episode_title"])
        self.assertEqual(body["show_title"], "Test TV Show")
        self.assertEqual(body["season_title"], "Season 1")
        self.assertEqual(body["overview"], "Overview 2.")
        self.assertFalse(body["watched"])
        self.assertEqual(
            (body["check"]["season_number"], body["check"]["episode_number"]), (1, 2)
        )
        self.assertTrue(body["previous_url"].endswith("/episode/1"))
        self.assertTrue(body["next_url"].endswith("/episode/3"))
        self.assertEqual([row["current"] for row in body["episodes"]], [False, True, False])
        self.assertEqual(body["guest_stars"][0]["role"], "Waiter")
        self.assertEqual(body["crew"][0], {"label": "Director", "name": "Some Director", "url": "/person/tmdb/6/some-director"})
        self.assertEqual(body["scores"][0]["rating"], "8.2")
        content = page.content.decode()
        for name in ("Guest Person", "Some Director"):
            self.assertIn(name, content)

    def test_season_edges(self, *_mocks):
        self.assertIsNone(self._api(1)["previous_url"])
        self.assertIsNone(self._api(3)["next_url"])

    def test_integration_tokens_cannot_call_it(self, *_mocks):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(user=self.user, name="episode", scopes=["catalog:read"])
        response = Client().get(
            reverse("api_episode_screen", args=["tmdb", "1668", 1, 2]), HTTP_X_API_KEY=raw
        )

        self.assertEqual(response.status_code, 403)
