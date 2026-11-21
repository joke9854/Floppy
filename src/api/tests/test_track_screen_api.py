"""The web track dialog's General tab (v2 P4-D1).

GET /api/v1/track/... reads the Django track modal's own form; the web posts
it back to the page's endpoints with `Accept: application/json`. These tests
hold the form to the page's fields and pin the exact-instant round trip.
"""

import datetime
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

import events.tasks
from app.models import Episode, Item, MediaTypes, Movie, Season, Sources, Status

JSON = {"HTTP_ACCEPT": "application/json"}


def normalize_initial_value(value, track_time=True):
    """Return what the page's date picker keeps from a field value (dateTimePicker.js)."""
    value = value.strip()
    if not value:
        return ""
    date_part, _, time_part = value.replace(" ", "T", 1).partition("T")
    if not time_part or not track_time:
        return date_part
    hour, minute, *rest = time_part.split(":")
    second = rest[0] if rest else ""
    try:
        zero = float(second) == 0
    except ValueError:
        zero = False
    return f"{date_part}T{hour}:{minute}" + (f":{second}" if second and not zero else "")


class TrackScreenTests(TestCase):
    """The General tab reads the page's form and saves through the page's views."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "tracker", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/matrix.jpg",
        )
        # Seconds and microseconds, as CineTrack plays carry them.
        self.start = datetime.datetime(2026, 3, 4, 20, 1, 7, 123456, tzinfo=datetime.UTC)
        self.end = datetime.datetime(2026, 3, 4, 22, 17, 59, 654321, tzinfo=datetime.UTC)
        self.movie = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
            score=7,
            start_date=self.start,
            end_date=self.end,
            notes="Good",
        )

    def _screen(self, media_type="movie", source="tmdb", media_id="603", **params):
        response = self.client.get(
            reverse("api_track_screen", args=[media_type, source, media_id]), params
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    @staticmethod
    def _post_data(screen, **changes):
        data = {}
        for field in [*screen["hidden"], *screen["fields"], screen["notes"]]:
            if field is None:
                continue
            value = field["value"]
            if field["kind"] in ("datetime", "date"):
                value = normalize_initial_value(value, field["kind"] == "datetime")
            data[field["name"]] = value
        data.update(changes)
        return {key: value for key, value in data.items() if value is not None}

    def test_fields_follow_the_page(self):
        page = self.client.get(
            reverse("track_modal", args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "603"])
        )
        page_fields = [bound.name for bound in page.context["general_fields"]]
        page_hidden = [bound.name for bound in page.context["general_hidden_fields"]]

        screen = self._screen()

        self.assertEqual([f["name"] for f in screen["fields"]], page_fields)
        self.assertEqual([f["name"] for f in screen["hidden"]], page_hidden)
        self.assertTrue(screen["tracked"])
        fields = {f["name"]: f for f in screen["fields"]}
        self.assertEqual(fields["status"]["kind"], "select")
        self.assertEqual(fields["status"]["choices"][0]["value"], "")
        self.assertEqual(fields["status"]["value"], Status.COMPLETED.value)
        self.assertEqual(fields["score"]["kind"], "number")
        self.assertIsNotNone(fields["score"]["max"])
        self.assertEqual(screen["notes"]["value"], "Good")
        self.assertTrue(screen["save_url"].startswith(reverse("media_save")))
        self.assertTrue(screen["delete_url"].startswith(reverse("media_delete")))
        self.assertEqual(screen["save_as_new"], "Save as another play")

    def test_an_untouched_update_keeps_the_exact_instants(self):
        screen = self._screen()

        response = self.client.post(screen["save_url"], self._post_data(screen), **JSON)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["saved"])
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.start_date, self.start)
        self.assertEqual(self.movie.end_date, self.end)
        self.assertEqual(Movie.objects.filter(item=self.item).count(), 1)

    def test_the_django_dialog_keeps_the_microseconds_too(self):
        page = self.client.get(
            reverse("track_modal", args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "603"])
        )

        # The picker's initialValue (escapejs turns the dashes into -).
        self.assertContains(page, "04 20:01:07.123456'")
        self.assertContains(page, "04 22:17:59.654321'")

    def test_whole_second_and_minute_instants_round_trip(self):
        self.movie.start_date = datetime.datetime(2026, 3, 4, 20, 1, 7, tzinfo=datetime.UTC)
        self.movie.end_date = datetime.datetime(2026, 3, 4, 22, 17, tzinfo=datetime.UTC)
        self.movie.save()
        screen = self._screen()

        self.client.post(screen["save_url"], self._post_data(screen), **JSON)

        self.movie.refresh_from_db()
        self.assertEqual(
            self.movie.start_date, datetime.datetime(2026, 3, 4, 20, 1, 7, tzinfo=datetime.UTC)
        )
        self.assertEqual(
            self.movie.end_date, datetime.datetime(2026, 3, 4, 22, 17, tzinfo=datetime.UTC)
        )

    def test_save_as_another_play_adds_a_row(self):
        from types import SimpleNamespace

        screen = self._screen()

        with patch(
            "app.save_views.ensure_item_metadata", return_value=SimpleNamespace(item=self.item)
        ):
            response = self.client.post(
                screen["save_url"],
                self._post_data(screen, save_as_new_entry="1", end_date="2026-05-01T21:00"),
                **JSON,
            )

        self.assertTrue(response.json()["saved"])
        self.assertEqual(Movie.objects.filter(item=self.item, user=self.user).count(), 2)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.end_date, self.end)

    def test_invalid_input_answers_with_the_form_errors(self):
        screen = self._screen()

        response = self.client.post(
            screen["save_url"], self._post_data(screen, score="not a score"), **JSON
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["saved"])
        self.assertIn("score", body["errors"])
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.score, 7)

    def test_delete(self):
        screen = self._screen()

        response = self.client.post(screen["delete_url"], self._post_data(screen), **JSON)

        self.assertEqual(response.json(), {"deleted": True})
        self.assertFalse(Movie.objects.filter(pk=self.movie.pk).exists())

    def test_plain_and_htmx_posts_answer_as_before(self):
        screen = self._screen()
        data = self._post_data(screen)

        self.assertEqual(self.client.post(screen["save_url"], data).status_code, 302)
        htmx = self.client.post(screen["save_url"], data, HTTP_HX_REQUEST="true")
        self.assertEqual(htmx.status_code, 200)
        self.assertIn("HX-Trigger", htmx.headers)

    def test_other_types_wait_for_later_slices(self):
        response = self.client.get(reverse("api_track_screen", args=["anime", "mal", "1"]))

        self.assertEqual(response.status_code, 400)

    def test_integration_tokens_cannot_call_it(self):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(
            user=self.user, name="track", scopes=["catalog:read", "progress:read"]
        )
        response = Client().get(
            reverse("api_track_screen", args=["movie", "tmdb", "603"]), HTTP_X_API_KEY=raw
        )

        self.assertEqual(response.status_code, 403)


class EpisodeTrackScreenTests(TestCase):
    """Episodes save through episode_save; a play keeps its exact instant."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "episodes", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        season_item = Item.objects.create(
            media_id="ep-1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Show",
            image="http://example.com/s.jpg",
            season_number=1,
        )
        self.season = Season.objects.create(
            item=season_item, user=self.user, status=Status.IN_PROGRESS.value
        )
        self.episode_item = Item.objects.create(
            media_id="ep-1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Pilot",
            image="http://example.com/e.jpg",
            season_number=1,
            episode_number=1,
        )
        self.watched = datetime.datetime(2026, 2, 1, 21, 30, 5, 250000, tzinfo=datetime.UTC)
        self.episode = Episode.objects.create(
            item=self.episode_item, related_season=self.season, end_date=self.watched
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_an_untouched_episode_update_keeps_the_instant(self, metadata_mock):
        metadata_mock.return_value = {
            "title": "Show",
            "episode_title": "Pilot",
            "season/1": {"episodes": [{"episode_number": 1}]},
        }
        response = self.client.get(
            reverse("api_track_screen", args=["episode", "tmdb", "ep-1"]),
            {"season_number": 1, "episode_number": 1},
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        screen = response.json()
        self.assertTrue(screen["save_url"].startswith(reverse("episode_save")))
        hidden = {f["name"]: f["value"] for f in screen["hidden"]}
        UUID(hidden["watch_operation_id"])

        saved = self.client.post(
            screen["save_url"], TrackScreenTests._post_data(screen), **JSON
        )

        self.assertEqual(saved.status_code, 200, saved.content)
        body = saved.json()
        self.assertTrue(body["saved"])
        UUID(body["watch_operation_id"])
        self.episode.refresh_from_db()
        self.assertEqual(self.episode.end_date, self.watched)
        self.assertEqual(Episode.objects.filter(item=self.episode_item).count(), 1)

    def test_season_and_episode_numbers_are_required(self):
        response = self.client.get(reverse("api_track_screen", args=["episode", "tmdb", "ep-1"]))

        self.assertEqual(response.status_code, 400)
