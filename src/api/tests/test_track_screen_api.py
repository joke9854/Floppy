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

        # The anime detail page's chip posts `anime` with the show's pk, and
        # names the title (also in the slot the score view re-renders).
        from django.template.loader import render_to_string

        chip = render_to_string(
            "app/components/detail_score_chip_slot.html",
            {
                "media": show,
                "current_instance": show_entry,
                "media_type": "anime",
                "user": self.user,
                "user_medias": [show_entry],
                "public_view": False,
                "csrf_token": "x",
            },
        )
        score_url = reverse("update_media_score", args=["anime", show_entry.id])
        self.assertIn(f"{score_url}?media_id=1429&amp;source=tmdb", chip)
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


class TrackerTrackScreenTests(TestCase):
    """P4-D2b: music artists and albums, podcast shows (the page's tracker dialog)."""

    def setUp(self):
        from app.models import (
            Album,
            AlbumTracker,
            Artist,
            ArtistTracker,
            PodcastShow,
            PodcastShowTracker,
        )

        cache.clear()
        self.credentials = {"username": "d2b", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.start = datetime.datetime(2026, 4, 1, 7, 5, 9, 111111, tzinfo=datetime.UTC)
        self.end = datetime.datetime(2026, 4, 2, 23, 58, 1, 999999, tzinfo=datetime.UTC)
        dates = {"start_date": self.start, "end_date": self.end}
        self.artist = Artist.objects.create(name="Radiohead")
        self.album = Album.objects.create(title="In Rainbows", artist=self.artist)
        self.show = PodcastShow.objects.create(podcast_uuid="show-uuid-1", title="The Daily")
        self.trackers = {
            "artist": ArtistTracker.objects.create(
                user=self.user, artist=self.artist, status=Status.COMPLETED.value, score=8, **dates
            ),
            "album": AlbumTracker.objects.create(
                user=self.user, album=self.album, status=Status.COMPLETED.value, score=8, **dates
            ),
            "podcast": PodcastShowTracker.objects.create(
                user=self.user, show=self.show, status=Status.COMPLETED.value, score=8, **dates
            ),
        }
        self.targets = {
            "artist": ("artist", "music", str(self.artist.id)),
            "album": ("album", "music", str(self.album.id)),
            "podcast": ("podcast", "pocketcasts", "show-uuid-1"),
        }
        self.pages = {
            "artist": reverse("artist_track_modal", args=[self.artist.id]),
            "album": reverse("album_track_modal", args=[self.album.id]),
            "podcast": reverse("podcast_show_track_modal", args=[self.show.id]),
        }

    def _screen(self, kind):
        response = self.client.get(reverse("api_track_screen", args=self.targets[kind]))
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_fields_follow_the_page(self, _populate):
        for kind in self.targets:
            with self.subTest(kind=kind):
                page = self.client.get(self.pages[kind])
                screen = self._screen(kind)

                self.assertEqual(
                    [f["name"] for f in screen["fields"]],
                    [b.name for b in page.context["general_fields"]],
                )
                self.assertEqual(
                    [f["name"] for f in screen["hidden"]],
                    [b.name for b in page.context["general_hidden_fields"]],
                )
                for bound in [
                    *page.context["general_fields"],
                    *page.context["general_hidden_fields"],
                ]:
                    self.assertIn(bound.field.widget.__class__.__name__, _KNOWN_WIDGETS, bound.name)
                self.assertTrue(screen["tracked"])
                self.assertEqual(screen["title"], str(page.context["title"]))
                self.assertNotIn("?", screen["save_url"])

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_an_untouched_update_keeps_the_tracker(self, _populate):
        for kind, tracker in self.trackers.items():
            with self.subTest(kind=kind):
                screen = self._screen(kind)

                response = self.client.post(
                    screen["save_url"], TrackScreenTests._post_data(screen), **JSON
                )

                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertTrue(body["saved"])
                self.assertEqual(body["instance_id"], tracker.id)
                tracker.refresh_from_db()
                self.assertEqual(tracker.start_date, self.start)
                self.assertEqual(tracker.end_date, self.end)
                self.assertEqual(tracker.status, Status.COMPLETED.value)
                self.assertEqual(float(tracker.score), 8.0)

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_errors_and_delete_answer_json(self, _populate):
        for kind, tracker in self.trackers.items():
            with self.subTest(kind=kind):
                screen = self._screen(kind)

                bad = self.client.post(
                    screen["save_url"], TrackScreenTests._post_data(screen, score="x"), **JSON
                )
                self.assertEqual(bad.status_code, 400, bad.content)
                self.assertIn("score", bad.json()["errors"])

                deleted = self.client.post(
                    screen["delete_url"], TrackScreenTests._post_data(screen), **JSON
                )
                self.assertEqual(deleted.json(), {"deleted": True})
                self.assertFalse(type(tracker).objects.filter(id=tracker.id).exists())

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_plain_and_htmx_posts_answer_as_before(self, _populate):
        screen = self._screen("album")
        data = TrackScreenTests._post_data(screen)

        plain = self.client.post(screen["save_url"], data)
        htmx = self.client.post(screen["save_url"], data, HTTP_HX_REQUEST="true")

        self.assertEqual(plain.status_code, 302)
        self.assertEqual(htmx.status_code, 204)
        self.assertIn("HX-Trigger", htmx.headers)

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_the_page_dialog_tells_an_existing_tracker_from_a_new_one(self, _populate):
        # The tracker forms have no instance_id, so the dialog's script reads
        # data-existing-entry; without it an empty end date was filled with now.
        tracked = self.client.get(self.pages["artist"])
        self.trackers["artist"].delete()
        untracked = self.client.get(self.pages["artist"])

        self.assertContains(tracked, 'data-existing-entry="true"')
        self.assertContains(untracked, 'data-existing-entry="false"')

    def test_songs_episodes_and_wrong_sources_keep_the_page(self):
        for args in (
            ("artist", "tmdb", str(self.artist.id)),
            ("album", "music", "not-a-number"),
            ("podcast", "pocketcasts", "episode-uuid"),
        ):
            with self.subTest(args=args):
                response = self.client.get(reverse("api_track_screen", args=args))
                self.assertEqual(response.status_code, 400)

    @patch("app.tasks_music.populate_album_tracks_batch.delay")
    def test_library_cards_open_their_tracker(self, _populate):
        artists = self.client.get(reverse("api_library_screen", args=["music"])).json()
        podcasts = self.client.get(reverse("api_library_screen", args=["podcast"])).json()

        tracks = [card["track"] for card in artists["results"]]
        self.assertIn(
            {
                "media_type": "artist",
                "source": "music",
                "media_id": str(self.artist.id),
                "season_number": None,
                "instance_id": None,
            },
            tracks,
        )
        podcast_track = podcasts["results"][0]["track"]
        self.assertEqual(
            (podcast_track["media_type"], podcast_track["source"], podcast_track["media_id"]),
            ("podcast", "pocketcasts", "show-uuid-1"),
        )
        for track in [*tracks, podcast_track]:
            response = self.client.get(
                reverse(
                    "api_track_screen",
                    args=[track["media_type"], track["source"], track["media_id"]],
                )
            )
            self.assertEqual(response.status_code, 200, response.content[:300])
            self.assertTrue(response.json()["tracked"])


class PlaysTrackScreenTests(TestCase):
    """P4-D3: the Episode Plays tab, read from the page's form and posted back."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d3", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="https://example.com/breaking-bad.jpg",
        )
        TV.objects.create(item=self.item, user=self.user, status=Status.IN_PROGRESS.value)

    def _patch_show(self):
        from app.services.metadata_resolution import MetadataResolutionResult
        from app.tests.views.test_track_modal import _tv_with_seasons_payload

        payload = {
            "media_id": "1396",
            "title": "Breaking Bad",
            "media_type": MediaTypes.TV.value,
            "source": Sources.TMDB.value,
            "image": "https://example.com/breaking-bad.jpg",
            "details": {"episodes": 3},
            "related": {"seasons": [{"season_number": 1, "season_title": "Season 1"}]},
        }
        metadata = patch(
            "app.providers.services.get_media_metadata",
            side_effect=lambda media_type, *_a, **_k: (
                _tv_with_seasons_payload("1396", Sources.TMDB.value, title="Breaking Bad")
                if media_type == "tv_with_seasons"
                else payload
            ),
        )
        resolution = patch(
            "app.views.metadata_resolution.resolve_detail_metadata",
            return_value=MetadataResolutionResult(
                display_provider=Sources.TMDB.value,
                identity_provider=Sources.TMDB.value,
                mapping_status="identity",
                header_metadata=payload,
                grouped_preview=None,
                provider_media_id="1396",
            ),
        )
        metadata.start()
        resolution.start()
        self.addCleanup(metadata.stop)
        self.addCleanup(resolution.stop)

    def _screen(self):
        response = self.client.get(reverse("api_track_screen", args=["tv", "tmdb", "1396"]))
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()

    def test_the_tab_follows_the_page(self):
        self._patch_show()
        page = self.client.get(reverse("track_modal", args=["tmdb", "tv", "1396"]))
        plays = self._screen()["plays"]

        form = page.context["episode_plays_form"]
        domain = page.context["episode_plays_domain"]
        self.assertEqual(plays["save_url"], reverse("episode_bulk_save"))
        self.assertEqual(plays["tab_label"], "Episode Plays")
        self.assertEqual(
            [f["name"] for f in plays["hidden"]], [b.name for b in form.hidden_fields()]
        )
        self.assertEqual(
            plays["first"],
            {
                "season_number": form.initial["first_season_number"],
                "episode_number": form.initial["first_episode_number"],
            },
        )
        self.assertEqual(plays["last"]["episode_number"], form.initial["last_episode_number"])
        self.assertEqual(plays["distribution_mode"]["value"], "air_date")
        self.assertEqual(
            [c["value"] for c in plays["write_mode"]["choices"]], ["add", "replace"]
        )
        self.assertEqual(
            [(e["order"], e["episode_number"], e["air_date"], e["runtime_minutes"])
             for e in plays["episodes"]["1"]],
            [(e["order"], e["episode_number"], e["air_date"], e["runtime_minutes"] or None)
             for e in domain["seasonEpisodeMap"]["1"]],
        )
        self.assertEqual(plays["seasons"][0]["season_number"], 1)

    def test_a_movie_has_no_tab(self):
        movie = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=movie, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(reverse("api_track_screen", args=["movie", "tmdb", "603"]))

        self.assertIsNone(response.json()["plays"])

    def test_the_posted_tab_queues_the_pages_job(self):
        self._patch_show()
        plays = self._screen()["plays"]
        data = {f["name"]: f["value"] for f in plays["hidden"]}
        data.update(
            first_season_number=plays["first"]["season_number"],
            first_episode_number=plays["first"]["episode_number"],
            last_season_number=plays["last"]["season_number"],
            last_episode_number=plays["last"]["episode_number"],
            write_mode="add",
            distribution_mode="even",
            start_date="2026-03-01T20:00",
            end_date="2026-03-03T22:00",
            episode_count=3,
        )

        with patch("app.tasks.bulk_episode_plays_task.apply_async") as job:
            job.return_value.id = "job-1"
            response = self.client.post(plays["save_url"], data, **JSON)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.json(),
            {"queued": True, "message": "Adding plays to 3 episodes.", "task_id": "job-1"},
        )
        kwargs = job.call_args.kwargs["kwargs"]
        self.assertEqual(
            (kwargs["media_id"], kwargs["first_episode_number"], kwargs["last_episode_number"]),
            ("1396", 1, 3),
        )
        self.assertEqual((kwargs["start_date_str"], kwargs["end_date_str"]),
                         ("2026-03-01T20:00", "2026-03-03T22:00"))

    def test_bulk_errors_answer_json_and_htmx_is_unchanged(self):
        base = {"media_id": "1396", "source": "tmdb", "media_type": "tv"}

        missing = self.client.post(reverse("episode_bulk_save"), base, **JSON)
        htmx = self.client.post(reverse("episode_bulk_save"), base, HTTP_HX_REQUEST="true")
        music = self.client.post(reverse("music_bulk_save"), {"context_kind": "song"}, **JSON)

        self.assertEqual(missing.status_code, 422)
        self.assertEqual(missing.json()["error"], "Start and end dates are required.")
        self.assertEqual(htmx.status_code, 422)
        self.assertIn("HX-Trigger", htmx.headers)
        self.assertEqual(music.status_code, 400)
        self.assertFalse(music.json()["queued"])


class DiscoverTrackScreenTests(TestCase):
    """P4-D4: the Discover tab hides or shows a title in Discover."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d4", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=self.item, user=self.user, status=Status.COMPLETED.value)

    def _discover(self):
        response = self.client.get(reverse("api_track_screen", args=["movie", "tmdb", "603"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()["discover"]

    def test_the_tab_follows_the_page_and_toggles(self):
        from app.models import DiscoverFeedback

        page = self.client.get(reverse("track_modal", args=["tmdb", "movie", "603"]))
        discover = self._discover()

        self.assertTrue(page.context["discover_tab_available"])
        self.assertEqual(
            discover,
            {"item_id": self.item.id, "hidden": False, "save_url": reverse("discover_toggle_hidden")},
        )

        hidden = self.client.post(
            discover["save_url"], {"item_id": self.item.id, "action": "hide"}, **JSON
        )
        self.assertEqual(
            hidden.json(), {"hidden": True, "message": 'Hidden "The Matrix" from Discover.'}
        )
        self.assertTrue(self._discover()["hidden"])
        self.assertTrue(DiscoverFeedback.objects.filter(user=self.user, item=self.item).exists())

        shown = self.client.post(
            discover["save_url"], {"item_id": self.item.id, "action": "unhide"}, **JSON
        )
        self.assertFalse(shown.json()["hidden"])
        self.assertFalse(self._discover()["hidden"])

    def test_the_page_post_still_renders_the_tab(self):
        response = self.client.post(
            reverse("discover_toggle_hidden"),
            {"item_id": self.item.id, "action": "hide"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "discover-tab-content")
        self.assertIn("discoverActionComplete", response.headers["HX-Trigger"])


class CollectionTrackScreenTests(TestCase):
    """P4-D5: an episode's Collection tab lists, adds and removes owned copies."""

    def setUp(self):
        EpisodeTrackScreenTests.setUp(self)
        from app.models import CollectionField, CollectionFieldGroup

        group = CollectionFieldGroup.objects.create(user=self.user, name="Shelf")
        self.boxed = CollectionField.objects.create(
            group=group, label="Boxed", field_type="checkbox", media_types=["episode"]
        )
        self.shelf = CollectionField.objects.create(
            group=group,
            label="Room",
            field_type="select",
            options=["Den", "Attic"],
            media_types=["episode"],
            position=1,
        )
        CollectionField.objects.create(
            group=group, label="Pages", field_type="number", media_types=["book"], position=2
        )
        patcher = patch(
            "app.models.providers.services.get_media_metadata",
            return_value={
                "title": "Show",
                "episode_title": "Pilot",
                "season/1": {"episodes": [{"episode_number": 1}]},
                "max_progress": 1,
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _collection(self):
        response = self.client.get(
            reverse("api_track_screen", args=["episode", "tmdb", "ep-1"]),
            {"season_number": 1, "episode_number": 1},
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        return response.json()["collection"]

    def test_the_tab_follows_the_page_adds_and_removes_copies(self):
        from app.models import CollectionEntry

        page = self.client.get(
            reverse("track_modal", args=["tmdb", "episode", "ep-1", 1]),
            {"episode_number": 1},
        )
        collection = self._collection()

        page_form = page.context["collection_context"]["form"]
        configured = page.context["collection_context"]["collection_fields"]
        self.assertEqual(
            [f["name"] for f in collection["fields"]],
            [b.name for b in page_form if b.name != "item" and b.name in configured],
        )
        kinds = {f["name"]: f["kind"] for f in collection["fields"]}
        self.assertEqual(kinds["media_type"], "select")
        self.assertEqual(kinds["is_3d"], "checkbox")
        self.assertEqual(kinds["purchase_price"], "number")
        self.assertIn(kinds["collected_at"], {"datetime", "date"})
        formats = [c["value"] for c in collection["fields"][0]["choices"]]
        self.assertEqual(formats[:3], ["", "4K Blu-ray", "Blu-ray"])
        self.assertEqual(collection["item_id"], self.episode_item.id)
        self.assertEqual(collection["entries"], [])
        self.assertEqual(collection["add_label"], "Add Copy")
        self.assertEqual(
            [(g["name"], [f["label"] for f in g["fields"]]) for g in collection["custom_groups"]],
            [("Shelf", ["Boxed", "Room"])],
        )

        added = self.client.post(
            collection["save_url"],
            {
                "item_id": collection["item_id"],
                "media_type": "Blu-ray",
                "resolution": "4K",
                "is_3d": "on",
                "purchase_price": "9.99",
                "purchase_location": "Amazon",
                f"custom_field_{self.boxed.id}": "on",
                f"custom_field_{self.shelf.id}": "Attic",
            },
            **JSON,
        )

        self.assertEqual(added.status_code, 200, added.content)
        self.assertEqual(added.json(), {"saved": True, "message": "Added Pilot to collection"})
        self.assertEqual(list(added.wsgi_request._messages), [])
        entry = CollectionEntry.objects.get(user=self.user, item=self.episode_item)
        self.assertEqual(
            entry.custom_field_values, {str(self.boxed.id): True, str(self.shelf.id): "Attic"}
        )

        collection = self._collection()
        self.assertEqual(collection["add_label"], "Add Another Copy")
        self.assertEqual(
            collection["entries"],
            [
                {
                    "id": entry.id,
                    "lines": ["Format: Blu-Ray", "4K • 3D", "$9.99 • Amazon"],
                    "remove_url": reverse("collection_remove", args=[entry.id]),
                }
            ],
        )
        custom = {f["label"]: f["value"] for f in collection["custom_groups"][0]["fields"]}
        self.assertEqual(custom, {"Boxed": "on", "Room": "Attic"})

        removed = self.client.post(collection["entries"][0]["remove_url"], **JSON)

        self.assertEqual(removed.json(), {"removed": True, "message": "Removed Pilot from collection"})
        self.assertFalse(CollectionEntry.objects.filter(id=entry.id).exists())

    def test_errors_answer_json_and_htmx_is_unchanged(self):
        from app.models import CollectionEntry

        collection = self._collection()
        bad = self.client.post(
            collection["save_url"], {"item_id": collection["item_id"], "purchase_price": "abc"}, **JSON
        )
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.json()["saved"])
        self.assertIn("purchase_price", bad.json()["errors"])

        missing = self.client.post(collection["save_url"], {"item_id": "nope"}, **JSON)
        self.assertEqual(missing.status_code, 404)
        self.assertFalse(missing.json()["saved"])

        htmx = self.client.post(
            reverse("collection_add"),
            {"item_id": collection["item_id"], "media_type": "DVD"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(htmx.json(), {"success": True, "message": "Added Pilot to collection"})
        self.assertEqual(CollectionEntry.objects.filter(item=self.episode_item).count(), 1)

    def test_other_types_have_no_tab(self):
        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(reverse("api_track_screen", args=["movie", "tmdb", "603"]))

        self.assertIsNone(response.json()["collection"])


@patch(
    "app.providers.tmdb.metadata_languages",
    return_value=[("", "Server Default (en-US)"), ("it-IT", "Italian")],
)
class MetadataTrackScreenTests(TestCase):
    """P4-D6a: the Metadata tab's provider, language, image and custom forms."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d6", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=self.item, user=self.user, status=Status.COMPLETED.value)

    def _screen(self):
        response = self.client.get(reverse("api_track_screen", args=["movie", "tmdb", "603"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_the_tab_follows_the_page(self, _languages):
        page = self.client.get(reverse("track_modal", args=["tmdb", "movie", "603"]))
        metadata = self._screen()["metadata"]

        self.assertTrue(page.context["metadata_tab_available"])
        self.assertEqual(
            [o["value"] for o in metadata["provider"]["options"]],
            [str(o.value) for o in page.context["metadata_provider_options"]],
        )
        self.assertEqual(metadata["provider"]["value"], page.context["display_provider"])
        self.assertEqual(
            metadata["language"]["options"],
            [{"value": "", "label": "Server Default (en-US)"}, {"value": "it-IT", "label": "Italian"}],
        )
        self.assertEqual(metadata["image"]["field"]["name"], "image_url")
        self.assertEqual(metadata["image"]["field"]["value"], "http://example.com/m.jpg")
        self.assertEqual(metadata["image"]["save_url"], reverse("update_item_image", args=[self.item.id]))
        self.assertIsNone(metadata["custom"])

    def test_language_and_image_save_as_json(self, _languages):
        metadata = self._screen()["metadata"]

        bad = self.client.post(metadata["language"]["save_url"], {"language": "xx"}, **JSON)
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.json()["saved"])
        saved = self.client.post(metadata["language"]["save_url"], {"language": "it-IT"}, **JSON)
        self.assertEqual(saved.json(), {"saved": True, "message": "Metadata language updated."})
        self.assertEqual(list(saved.wsgi_request._messages), [])
        self.assertEqual(self._screen()["metadata"]["language"]["value"], "it-IT")

        empty = self.client.post(metadata["image"]["save_url"], {"image_url": ""}, **JSON)
        self.assertEqual(empty.status_code, 400)
        self.assertIn("image_url", empty.json()["errors"])
        image = self.client.post(
            metadata["image"]["save_url"], {"image_url": "http://example.com/new.jpg"}, **JSON
        )
        self.assertEqual(image.json(), {"saved": True, "message": "Image URL updated."})
        self.item.refresh_from_db()
        self.assertEqual(self.item.image, "http://example.com/new.jpg")

    def test_the_general_form_carries_the_image_untouched(self, _languages):
        screen = self._screen()
        data = TrackScreenTests._post_data(screen)
        data["image_url"] = screen["metadata"]["image"]["field"]["value"]

        saved = self.client.post(screen["save_url"], data, **JSON)

        self.assertEqual(saved.status_code, 200, saved.content)
        self.item.refresh_from_db()
        self.assertEqual(self.item.image, "http://example.com/m.jpg")

    @patch("app.metadata_sync_views._resolve_current_display_metadata_payload")
    def test_custom_provider_opens_the_custom_form(self, payload, _languages):
        payload.return_value = {"title": "The Matrix", "details": {"runtime": "2h 16m"}}
        metadata = self._screen()["metadata"]
        if "manual" not in [o["value"] for o in metadata["provider"]["options"]]:
            self.skipTest("Movies offer no Custom provider here.")

        bad = self.client.post(metadata["provider"]["save_url"], {"provider": "nope"}, **JSON)
        self.assertEqual(bad.status_code, 400)
        chosen = self.client.post(metadata["provider"]["save_url"], {"provider": "manual"}, **JSON)
        self.assertEqual(chosen.json(), {"saved": True, "message": "Metadata provider updated."})

        metadata = self._screen()["metadata"]
        self.assertEqual(metadata["provider"]["value"], "manual")
        self.assertIsNone(metadata["image"])
        custom = metadata["custom"]
        self.assertTrue(custom["fields"])
        self.assertTrue(all(f["name"].startswith("metadata-") for f in custom["fields"]))
        kinds = {f["name"]: f["kind"] for f in custom["fields"]}
        self.assertEqual(kinds.get("metadata-release_date"), "date")
        self.assertEqual(kinds.get("metadata-synopsis"), "textarea")
        page = self.client.get(reverse("track_modal", args=["tmdb", "movie", "603"]))
        self.assertEqual(
            [f["name"] for f in custom["fields"]],
            [b.html_name for b in page.context["manual_metadata_form"]],
        )

        untouched = {f["name"]: f["value"] for f in custom["fields"]}
        kept = self.client.post(custom["save_url"], untouched, **JSON)
        self.assertEqual(kept.status_code, 200, kept.content)
        self.assertTrue(kept.json()["saved"])
        self.assertEqual(
            {f["name"]: f["value"] for f in self._screen()["metadata"]["custom"]["fields"]}, untouched
        )

        title = next(f["name"] for f in custom["fields"] if f["name"] == "metadata-title")
        changed = self.client.post(custom["save_url"], {**untouched, title: "The Matrix (Custom)"}, **JSON)
        self.assertEqual(changed.json(), {"saved": True, "message": "Custom metadata updated."})

    def test_a_plain_post_still_redirects(self, _languages):
        response = self.client.post(
            reverse("update_metadata_language_preference", args=["tmdb", "movie", "603"]),
            {"language": "it-IT", "return_url": "/"},
        )
        self.assertEqual(response.status_code, 302)

    @patch("app.providers.services.get_media_metadata")
    def test_an_untracked_title_saves_its_image_with_the_general_form(self, metadata, _languages):
        metadata.return_value = {
            "title": "The Matrix",
            "image": "http://example.com/m.jpg",
            "max_progress": 1,
            "details": {},
        }
        Movie.objects.filter(item=self.item).delete()

        image = self._screen()["metadata"]["image"]

        self.assertEqual(image["save_url"], "")
        self.assertEqual(image["field"]["name"], "image_url")


class MetadataPickerTests(TestCase):
    """P4-D6b: the Metadata tab's searches and pickers answer JSON."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d6b", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _movie(self):
        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/m.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        return item

    @patch("app.metadata_sync_views.library_actions.remap_metadata_provider")
    @patch("app.metadata_sync_views.services.search")
    @patch("app.providers.tmdb.metadata_languages", return_value=[("", "Default")])
    def test_remap_search_and_save(self, _languages, search, remap):
        from app.models import MetadataProviderPreference

        item = self._movie()
        MetadataProviderPreference.objects.create(user=self.user, item=item, provider="manual")
        screen = self.client.get(reverse("api_track_screen", args=["movie", "tmdb", "603"])).json()
        remap_block = screen["metadata"]["provider"]["remap"]
        self.assertEqual(remap_block["provider"], "manual")
        self.assertEqual(remap_block["prompt"], "Wrong match? Search Custom to pick the correct title.")

        search.return_value = {"results": [{"media_id": "77", "title": "Matrix", "image": "", "year": 1999}]}
        found = self.client.get(remap_block["search_url"] + "&q=matrix", **JSON)
        self.assertEqual(
            found.json(), {"results": [{"media_id": "77", "title": "Matrix", "image": None, "year": "1999"}]}
        )

        bad = self.client.post(remap_block["save_url"], {"provider": "tmdb", "provider_media_id": "77"}, **JSON)
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(bad.json()["error"], "That remap target is not valid for this title.")
        saved = self.client.post(
            remap_block["save_url"], {"provider": "manual", "provider_media_id": "77"}, **JSON
        )
        self.assertEqual(saved.json()["message"], "Remapped to the selected match.")
        self.assertTrue(saved.json()["saved"])
        self.assertEqual(list(saved.wsgi_request._messages), [])
        remap.assert_called_once_with(self.user, item, "movie", "manual", "77")

        page = self.client.post(remap_block["save_url"], {"provider": "manual", "provider_media_id": "77"})
        self.assertEqual(page.status_code, 302)

    @patch("app.metadata_sync_views.library_migration.migrate_library_item")
    @patch("app.metadata_sync_views.library_migration.get_move_context")
    @patch("app.metadata_sync_views.services.search")
    def test_library_move_search_and_move(self, search, move_context, migrate):
        from app.services.library_migration import LibraryMigrationError

        item = self._movie()
        move_context.return_value = {
            "target_media_type": "anime",
            "target_source": "mal",
            "target_label": "Anime",
            "target_source_label": "MyAnimeList",
        }
        search.return_value = {"results": [{"media_id": "1", "title": "Show", "image": "", "year": 2001}]}
        found = self.client.get(
            reverse("search_library_move_candidates", kwargs={"item_id": item.id}), {"q": "show"}, **JSON
        )
        self.assertEqual(found.json()["results"][0]["media_id"], "1")

        move_url = reverse("move_library_item", kwargs={"item_id": item.id})
        migrate.side_effect = LibraryMigrationError("Already tracked there.")
        failed = self.client.post(move_url, {"target_media_id": "1"}, **JSON)
        self.assertEqual(failed.json(), {"saved": False, "error": "Already tracked there."})

        migrate.side_effect = None
        migrate.return_value = item
        moved = self.client.post(move_url, {"target_media_id": "1"}, **JSON)
        self.assertEqual(moved.json()["message"], "Moved tracking to The Matrix.")
        self.assertTrue(moved.json()["location"].startswith("/details/tmdb/movie/603/"))

    @patch("app.track_modal_views.hardcover.editions")
    @patch("app.metadata_sync_views.hardcover.editions")
    def test_hardcover_edition_picker(self, list_editions, modal_editions):
        from app.models import HardcoverEditionPreference

        item = Item.objects.create(
            media_id="778812",
            source=Sources.HARDCOVER.value,
            media_type=MediaTypes.BOOK.value,
            title="Eye of the Needle",
            image="http://example.com/en.jpg",
            number_of_pages=354,
        )
        Book.objects.create(item=item, user=self.user, status=Status.IN_PROGRESS.value)
        editions = [
            {"id": "24008419", "title": "Die Nadel", "image": "", "format": "Paperback", "language": "German"},
            {"id": "1", "title": "Eye of the Needle", "image": "", "format": "", "language": "English"},
        ]
        list_editions.return_value = modal_editions.return_value = editions
        HardcoverEditionPreference.objects.create(user=self.user, item=item, edition_id="24008419")

        response = self.client.get(reverse("api_track_screen", args=["book", "hardcover", "778812"]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        edition = response.json()["metadata"]["edition"]
        self.assertEqual(edition["save_url"], reverse("set_hardcover_edition", kwargs={"item_id": item.id}))
        self.assertEqual(edition["selected"]["title"], "Die Nadel")
        self.assertEqual(edition["selected"]["lines"], ["German · Paperback"])

        found = self.client.get(edition["search_url"], {"q": "eye"}, **JSON)
        self.assertEqual(
            found.json()["results"],
            [{"value": "1", "title": "Eye of the Needle", "image": None, "lines": ["English"], "selected": False}],
        )
        empty = self.client.post(edition["save_url"], {"edition_id": ""}, **JSON)
        self.assertEqual(empty.json(), {"saved": False, "error": "Select an edition to use."})
        saved = self.client.post(edition["save_url"], {"edition_id": "1"}, **JSON)
        self.assertEqual(saved.json()["message"], "Edition updated.")
        self.assertTrue(saved.json()["saved"])

    @patch("app.providers.musicbrainz.get_release_group_genres", return_value=[])
    @patch("app.providers.musicbrainz.get_release")
    @patch("app.music_album_views.musicbrainz.get_release_group_releases")
    def test_album_release_picker(self, releases, get_release, _genres):
        from app.models import Album, AlbumTracker, Artist

        artist = Artist.objects.create(name="Test Artist")
        album = Album.objects.create(
            title="Test Album",
            artist=artist,
            musicbrainz_release_id="representative-release",
            musicbrainz_release_group_id="release-group",
            tracks_populated=True,
            image="https://example.com/default.jpg",
        )
        AlbumTracker.objects.create(user=self.user, album=album, status=Status.COMPLETED.value)
        release = {
            "release_id": "release-1",
            "title": "Original Pressing",
            "release_date": "1977",
            "country": "US",
            "status": "official",
            "packaging": "Jewel Case",
            "format": "CD",
            "label": "Example Records",
            "barcode": "0123",
            "track_count": 9,
            "image": "",
            "release_group_id": "release-group",
            "tracks": [],
        }
        releases.return_value = [release]
        get_release.return_value = release

        screen = self.client.get(reverse("api_track_screen", args=["album", "music", str(album.id)]))
        self.assertEqual(screen.status_code, 200, screen.content[:300])
        picker = screen.json()["metadata"]["release"]
        self.assertEqual(picker["save_url"], reverse("set_music_release", kwargs={"album_id": album.id}))
        self.assertIsNone(picker["selected"])

        found = self.client.get(picker["search_url"], **JSON)
        self.assertEqual(
            found.json()["results"][0]["lines"],
            ["1977 · US · Official", "CD · Jewel Case · Example Records · 9 tracks", "Barcode: 0123"],
        )
        saved = self.client.post(picker["save_url"], {"release_id": "release-1"}, **JSON)
        self.assertTrue(saved.json()["saved"], saved.content)


class GroupedAnimeConversionTests(TestCase):
    """P4-D6c: Convert to Grouped Series, previewed and posted as JSON."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "d6c", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.item = Item.objects.create(
            media_id="9253",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Steins;Gate",
            image="http://example.com/a.jpg",
        )
        Anime.objects.create(item=self.item, user=self.user, status=Status.COMPLETED.value)

    def test_the_preview_reads_as_the_page(self):
        from api.track_screen import _grouped

        context = {
            "can_migrate_grouped_anime": True,
            "grouped_preview": {
                "title": "Steins;Gate",
                "related": {
                    "seasons": [
                        {"season_number": 0, "max_progress": 2},
                        {
                            "season_number": 1,
                            "episode_count": 24,
                            "is_mapped_target": True,
                            "mapped_episode_start": 1,
                            "mapped_episode_end": 24,
                        },
                        {"season_number": 2},
                    ]
                },
            },
            "grouped_preview_target": {"season_title": "Season 1", "episode_start": 1, "episode_end": 24},
            "identity_provider": "mal",
            "display_provider": "tmdb",
            "user": self.user,
        }
        route = {"source": "mal", "media_type": "anime", "media_id": "9253"}

        grouped = _grouped(context, route)

        self.assertEqual(grouped["save_url"], reverse("migrate_grouped_anime", kwargs=route))
        self.assertEqual(grouped["provider"], "tmdb")
        self.assertEqual(
            grouped["lines"],
            [
                "See how this MAL entry will map into a single show with seasons before you convert it.",
                "TMDB organizes this anime as Steins;Gate, with seasons grouped under one main show.",
                "This MAL entry would convert to Season 1, episodes 1-24.",
                "Nothing changes until you click Convert to Grouped Series. "
                "Your existing MAL entry stays in place until then.",
            ],
        )
        self.assertEqual(
            [(s["label"], s["target"], s["mapped"], s["episodes"]) for s in grouped["seasons"]],
            [
                ("Specials", False, "", "2 episodes"),
                ("Season 1", True, "MAL episodes: E1-E24", "24 episodes"),
                ("Season 2", False, "", "? episodes"),
            ],
        )
        self.assertIsNone(_grouped({**context, "can_migrate_grouped_anime": False}, route))

    @patch("app.metadata_sync_views.anime_migration.migrate_flat_anime_to_grouped")
    def test_convert_answers_json(self, migrate):
        url = reverse("migrate_grouped_anime", args=["mal", "anime", "9253"])

        refused = self.client.post(url, {"provider": "mal"}, **JSON)
        self.assertEqual(
            refused.json(), {"saved": False, "error": "Choose TMDB or TVDB before migrating this anime."}
        )

        grouped_item = Item.objects.create(
            media_id="42509",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Steins;Gate",
            image="http://example.com/t.jpg",
        )
        migrate.return_value.grouped_tv.item = grouped_item
        converted = self.client.post(url, {"provider": "tmdb"}, **JSON)

        self.assertEqual(converted.json()["message"], "Migrated this anime into grouped series tracking.")
        self.assertTrue(converted.json()["location"].startswith("/details/tmdb/anime/42509/"))
        self.assertEqual(list(converted.wsgi_request._messages), [])
