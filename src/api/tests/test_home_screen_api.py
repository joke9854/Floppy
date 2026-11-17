from datetime import timedelta
from http import HTTPStatus as HTTP  # noqa: N814

from django.test import Client
from django.urls import reverse

from app.models import Status
from app.tests.test_home_sections import HomeSectionsTests, InProgressFixtures
from events.models import Event
from integrations.models import IntegrationToken

URL = reverse("api_home_sections")


def _token(user, scopes):
    _, raw = IntegrationToken.generate(user=user, name="home screen test", scopes=scopes)
    return raw


class HomeScreenAccessTests(InProgressFixtures):
    """GET /api/v1/home/sections/: who may read it."""

    def test_requires_a_credential(self):
        self.assertEqual(Client().get(URL).status_code, HTTP.FORBIDDEN)

    def test_the_browser_session_reads_it(self):
        response = self.client.get(URL)

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(),
            {
                "summary": {"catch_up": 0, "catch_up_shows": 0, "airing_count": 0},
                "in_progress": [],
                "in_progress_kinds": [],
                "airing": [],
                "recent": [],
                "coming_soon": [],
            },
        )

    def test_catalog_read_reads_it_and_progress_read_does_not(self):
        allowed = self.client.get(URL, HTTP_X_API_KEY=_token(self.user, ["catalog:read"]))
        denied = self.client.get(URL, HTTP_X_API_KEY=_token(self.user, ["progress:read"]))

        self.assertEqual(allowed.status_code, HTTP.OK)
        self.assertEqual(denied.status_code, HTTP.FORBIDDEN)


class HomeScreenInProgressTests(InProgressFixtures):
    """In Progress cards carry what the progress card shows and what its check posts."""

    def test_a_show_names_its_part_watched_episode_and_the_check_marks_it(self):
        self._show(
            "1",
            Status.IN_PROGRESS.value,
            released=4,
            watched=[1],
            part_watched=2,
            part_position=1200,
            part_duration=2700,
        )

        card = self.client.get(URL).json()["in_progress"][0]

        self.assertEqual(card["kind"], "show")
        self.assertEqual(card["title"], "Show 1")
        self.assertEqual(card["episode"]["season_number"], 1)
        self.assertEqual(card["episode"]["episode_number"], 2)
        self.assertEqual(
            card["check"],
            {
                "source": "tmdb",
                "media_id": "1",
                "season_number": 1,
                "episode_number": 2,
                "library_media_type": card["check"]["library_media_type"],
            },
        )
        self.assertIn("/season/1/episode/2", card["url"])
        self.assertEqual(card["remaining_seconds"], 1500)
        self.assertEqual(card["remaining_label"], "25m")
        # The resume time replaces the episodes-left count, as on the card.
        self.assertIsNone(card["episodes_left"])
        self.assertIsNone(card["backdrop"])
        self.assertTrue(card["poster"])

    def test_a_show_without_a_resume_time_counts_episodes_left(self):
        self._show("2", Status.IN_PROGRESS.value, released=3, watched=[1])

        card = self.client.get(URL).json()["in_progress"][0]

        self.assertEqual(card["episode"]["episode_number"], 2)
        self.assertIsNone(card["remaining_seconds"])
        self.assertEqual(card["episodes_left"], 2)

    def test_both_kinds_present_lists_both_for_the_filter(self):
        self._movie("630", Status.IN_PROGRESS.value, position=1800, duration=7200)
        self._show("2", Status.IN_PROGRESS.value, released=3, watched=[1])

        body = self.client.get(URL).json()

        self.assertEqual(body["in_progress_kinds"], ["movie", "show"])
        movie = next(card for card in body["in_progress"] if card["kind"] == "movie")
        self.assertIsNone(movie["check"])
        self.assertEqual(movie["progress_percent"], 25)
        self.assertEqual(movie["remaining_label"], "1h 30m")


class HomeScreenSectionsTests(HomeSectionsTests):
    """The header counts, Airing This Week and Recently Watched."""

    def test_summary_and_airing_carry_day_label_and_tag(self):
        for number, days in ((9, 1), (10, 2)):
            Event.objects.create(
                item=self.season_item,
                content_number=number,
                datetime=self.now + timedelta(days=days),
            )

        body = self.client.get(URL).json()

        self.assertEqual(body["summary"], {"catch_up": 4, "catch_up_shows": 1, "airing_count": 2})
        self.assertEqual(
            [(release["label"], release["tag"]) for release in body["airing"]],
            [("S1 E9", None), ("S1 E10", "finale")],
        )
        first = body["airing"][0]
        self.assertEqual(first["title"], "Friends")
        self.assertIn("/season/1/episode/9", first["url"])
        self.assertFalse(first["is_today"])
        self.assertTrue(first["day"])

    def test_recently_watched_says_when(self):
        body = self.client.get(URL).json()

        self.assertEqual([card["title"] for card in body["recent"]], ["Friends"])
        self.assertTrue(body["recent"][0]["subtitle"])
