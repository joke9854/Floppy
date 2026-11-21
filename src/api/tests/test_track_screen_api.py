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
from app.models import (
    TV,
    Anime,
    BoardGame,
    Book,
    Comic,
    ComicIssue,
    Episode,
    Game,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)

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

    def test_music_and_podcasts_keep_their_own_dialogs(self):
        for media_type in (MediaTypes.MUSIC.value, MediaTypes.PODCAST.value):
            response = self.client.get(
                reverse("api_track_screen", args=[media_type, "manual", "1"])
            )
            self.assertEqual(response.status_code, 400, media_type)

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


# Widgets the web dialog draws; a new one must get a drawing first (P4-D2).
_KNOWN_WIDGETS = {
    "HiddenInput",
    "NumberInput",
    "Select",
    "TextInput",
    "Textarea",
    "DateTimeInput",
    "DateInput",
}

_STANDARD_MODELS = {
    MediaTypes.ANIME.value: Anime,
    MediaTypes.MANGA.value: Manga,
    MediaTypes.GAME.value: Game,
    MediaTypes.BOOK.value: Book,
    MediaTypes.COMIC.value: Comic,
    MediaTypes.COMIC_ISSUE.value: ComicIssue,
    MediaTypes.BOARDGAME.value: BoardGame,
}


class StandardTypesTrackScreenTests(TestCase):
    """P4-D2: every type the page's standard dialog edits, from manual items."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d2", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.start = datetime.datetime(2026, 2, 1, 9, 30, 11, 250000, tzinfo=datetime.UTC)
        self.end = datetime.datetime(2026, 2, 3, 21, 4, 52, 987654, tzinfo=datetime.UTC)

    def _tracked(self, media_type, progress=3, status=Status.COMPLETED.value, **item_fields):
        item = Item.objects.create(
            media_id=f"{media_type}-1",
            source=Sources.MANUAL.value,
            media_type=media_type,
            title=f"A {media_type}",
            image="http://example.com/a.jpg",
            **item_fields,
        )
        media = _STANDARD_MODELS[media_type].objects.create(
            item=item,
            user=self.user,
            status=status,
            score=6,
            progress=progress,
            start_date=self.start,
            end_date=self.end,
        )
        return item, media

    def _screen(self, item, **params):
        response = self.client.get(
            reverse("api_track_screen", args=[item.media_type, item.source, item.media_id]),
            params,
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    def test_fields_follow_the_page_for_every_type(self):
        for media_type in _STANDARD_MODELS:
            with self.subTest(media_type=media_type):
                item, _ = self._tracked(media_type)
                page = self.client.get(
                    reverse("track_modal", args=[item.source, media_type, item.media_id])
                )
                screen = self._screen(item)

                self.assertEqual(
                    [f["name"] for f in screen["fields"]],
                    [b.name for b in page.context["general_fields"]],
                )
                self.assertEqual(
                    [f["name"] for f in screen["hidden"]],
                    [b.name for b in page.context["general_hidden_fields"]],
                )
                self.assertTrue(screen["tracked"])
                self.assertTrue(screen["save_url"].startswith(reverse("media_save")))
                for bound in [
                    *page.context["general_fields"],
                    *page.context["general_hidden_fields"],
                ]:
                    self.assertIn(bound.field.widget.__class__.__name__, _KNOWN_WIDGETS, bound.name)

    def test_an_untracked_title_opens_empty(self):
        item = Item.objects.create(
            media_id="game-2",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.GAME.value,
            title="New game",
            image="http://example.com/a.jpg",
        )

        screen = self._screen(item)

        self.assertFalse(screen["tracked"])
        self.assertEqual(screen["delete_url"], "")

    def test_an_untouched_update_keeps_dates_and_progress_for_every_type(self):
        for media_type, model in _STANDARD_MODELS.items():
            with self.subTest(media_type=media_type):
                item, media = self._tracked(media_type, progress=95)
                screen = self._screen(item)

                response = self.client.post(
                    screen["save_url"], TrackScreenTests._post_data(screen), **JSON
                )

                self.assertEqual(response.status_code, 200, response.content)
                self.assertTrue(response.json()["saved"])
                media.refresh_from_db()
                self.assertEqual(media.start_date, self.start)
                self.assertEqual(media.end_date, self.end)
                self.assertEqual(media.progress, 95)
                self.assertEqual(model.objects.filter(item=item).count(), 1)

    def test_game_progress_is_hours_and_minutes(self):
        item, media = self._tracked(MediaTypes.GAME.value, progress=125)

        screen = self._screen(item)

        progress = {f["name"]: f for f in screen["fields"]}["progress"]
        self.assertEqual(progress["kind"], "text")
        self.assertEqual(progress["value"], "2h 05min")
        response = self.client.post(
            screen["save_url"], TrackScreenTests._post_data(screen, progress="3h 10min"), **JSON
        )
        self.assertEqual(response.status_code, 200, response.content)
        media.refresh_from_db()
        self.assertEqual(media.progress, 190)
        self.assertEqual(media.start_date, self.start)

    def test_book_progress_in_percent_round_trips(self):
        self.user.book_comic_manga_progress_percentage = True
        self.user.save(update_fields=["book_comic_manga_progress_percentage"])
        item, media = self._tracked(
            MediaTypes.BOOK.value,
            progress=337,
            status=Status.IN_PROGRESS.value,
            number_of_pages=480,
        )

        screen = self._screen(item)

        progress = {f["name"]: f for f in screen["fields"]}["progress"]
        self.assertEqual(progress["value"], "70.2")
        self.assertEqual(progress["max"], "100")
        response = self.client.post(screen["save_url"], TrackScreenTests._post_data(screen), **JSON)
        self.assertEqual(response.status_code, 200, response.content)
        media.refresh_from_db()
        self.assertEqual(media.progress, 337)

    def test_an_untouched_percentage_keeps_a_long_books_pages(self):
        self.user.book_comic_manga_progress_percentage = True
        self.user.save(update_fields=["book_comic_manga_progress_percentage"])
        item, media = self._tracked(
            MediaTypes.BOOK.value,
            progress=337,
            status=Status.IN_PROGRESS.value,
            number_of_pages=1500,
        )
        screen = self._screen(item)
        # 337 of 1500 shows as 22.5%, which converts back to 338.
        self.assertEqual({f["name"]: f for f in screen["fields"]}["progress"]["value"], "22.5")

        # The web dialog, then the page's own (plain) post.
        self.client.post(screen["save_url"], TrackScreenTests._post_data(screen), **JSON)
        media.refresh_from_db()
        self.assertEqual(media.progress, 337)
        self.client.post(screen["save_url"], TrackScreenTests._post_data(screen))
        media.refresh_from_db()
        self.assertEqual(media.progress, 337)

        changed = self.client.post(
            screen["save_url"], TrackScreenTests._post_data(screen, progress="50"), **JSON
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        media.refresh_from_db()
        self.assertEqual(media.progress, 750)

    def _open_card(self, track):
        params = {}
        if track["season_number"] is not None:
            params["season_number"] = track["season_number"]
        if track["instance_id"] is not None:
            params["instance_id"] = track["instance_id"]
        response = self.client.get(
            reverse(
                "api_track_screen", args=[track["media_type"], track["source"], track["media_id"]]
            ),
            params,
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    def test_the_library_card_opens_what_the_page_button_opens(self):
        game, game_entry = self._tracked(MediaTypes.GAME.value)
        movie_item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/a.jpg",
        )
        movie = Movie.objects.create(item=movie_item, user=self.user, status=Status.COMPLETED.value)

        games = self.client.get(reverse("api_library_screen", args=["game"])).json()
        movies = self.client.get(reverse("api_library_screen", args=["movie"])).json()

        self.assertEqual(
            games["results"][0]["track"],
            {
                "media_type": "game",
                "source": "manual",
                "media_id": game.media_id,
                "season_number": None,
                "instance_id": game_entry.id,
            },
        )
        movie_track = movies["results"][0]["track"]
        self.assertEqual(
            (movie_track["media_type"], movie_track["media_id"], movie_track["instance_id"]),
            ("movie", "603", movie.id),
        )
        self.assertEqual(self._open_card(movie_track)["title"], "The Matrix")
        self.assertEqual(self._open_card(games["results"][0]["track"])["title"], game.title)

    def test_a_season_card_opens_its_season(self):
        from api.library_screen import _track_target

        show = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Game of Thrones",
            image="http://example.com/a.jpg",
        )
        show_entry = TV.objects.create(item=show, user=self.user, status=Status.IN_PROGRESS.value)
        season_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Game of Thrones",
            image="http://example.com/a.jpg",
            season_number=2,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=show_entry,
            status=Status.IN_PROGRESS.value,
        )

        track = _track_target(season)

        self.assertEqual(
            track,
            {
                "media_type": "season",
                "source": "tmdb",
                "media_id": "1399",
                "season_number": 2,
                "instance_id": season.id,
            },
        )
        self.assertEqual(_track_target(show_entry)["instance_id"], show_entry.id)

    @patch("app.models.TV._start_next_available_season")
    def test_a_show_filed_as_anime_opens_the_show_not_an_anime_with_its_id(self, _next_season):
        show = Item.objects.create(
            media_id="1429",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            library_media_type=MediaTypes.ANIME.value,
            title="Attack on Titan",
            image="http://example.com/a.jpg",
        )
        show_entry = TV.objects.create(item=show, user=self.user, status=Status.IN_PROGRESS.value)
        # A MAL anime whose row has the show's pk: the page's `anime`
        # instance_id lookup would open it.
        mal = Item.objects.create(
            media_id="16498",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            image="http://example.com/a.jpg",
        )
        Anime.objects.create(id=show_entry.id, item=mal, user=self.user, status=Status.COMPLETED.value)

        anime = self.client.get(reverse("api_library_screen", args=["anime"])).json()

        track = next(c["track"] for c in anime["results"] if c["key"] == show.id)
        # The page's button opens a TMDB show filed as anime as `anime`.
        self.assertEqual(track["media_type"], "anime")
        self.assertIsNone(track["instance_id"])
        screen = self._open_card(track)
        self.assertTrue(screen["tracked"])
        self.assertEqual(screen["title"], "Attack on Titan")
        hidden = {f["name"]: f["value"] for f in screen["hidden"]}
        self.assertEqual(hidden["instance_id"], str(show_entry.id))

        # The page's own table button passes the show's pk as an `anime` instance_id.
        page = self.client.get(
            reverse("track_modal", args=["tmdb", "anime", "1429"]),
            {"instance_id": show_entry.id},
        )
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context["media"], show_entry)

        # Saving and deleting the show must not touch the anime with its pk.
        saved = self.client.post(
            screen["save_url"], TrackScreenTests._post_data(screen, score="4"), **JSON
        )
        self.assertEqual(saved.status_code, 200, saved.content)
        show_entry.refresh_from_db()
        anime_entry = Anime.objects.get(id=show_entry.id)
        self.assertEqual(show_entry.score, 4)
        self.assertIsNone(anime_entry.score)
        deleted = self.client.post(
            screen["delete_url"], TrackScreenTests._post_data(screen), **JSON
        )
        self.assertEqual(deleted.status_code, 200, deleted.content)
        self.assertFalse(TV.objects.filter(id=show_entry.id).exists())
        self.assertTrue(Anime.objects.filter(id=show_entry.id).exists())

    @patch("app.models.TV._start_next_available_season")
    def test_the_detail_score_chip_rates_the_show_not_an_anime_with_its_id(self, _next_season):
        show = Item.objects.create(
            media_id="1429",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            library_media_type=MediaTypes.ANIME.value,
            title="Attack on Titan",
            image="http://example.com/a.jpg",
        )
        show_entry = TV.objects.create(item=show, user=self.user, status=Status.IN_PROGRESS.value)
        mal = Item.objects.create(
            media_id="16498",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            image="http://example.com/a.jpg",
        )
        anime_entry = Anime.objects.create(
            id=show_entry.id, item=mal, user=self.user, status=Status.COMPLETED.value
        )

        # The anime detail page's chip posts `anime` with the show's pk.
        response = self.client.post(
            reverse("update_media_score", args=["anime", show_entry.id])
            + "?media_id=1429&source=tmdb",
            {"score": 8},
        )

        self.assertLess(response.status_code, 400, response.content[:300])
        show_entry.refresh_from_db()
        anime_entry.refresh_from_db()
        self.assertEqual(show_entry.score, 8)
        self.assertIsNone(anime_entry.score)

    def test_a_media_id_with_a_slash_opens(self):
        item, _ = self._tracked(MediaTypes.BOOK.value)
        item.media_id = "works/OL1W"
        item.save(update_fields=["media_id"])

        screen = self._screen(item)

        self.assertTrue(screen["tracked"])
