"""The web activity sessions dialog, ratings graphs and studio page (v2 P4-L3b).

Each is built by the Django page's own builder, so these tests check the API
says what the page renders. Provider calls are patched, so they run offline.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.tests.test_detail_screen_api import _metadata
from app.models import (
    Book,
    Game,
    Item,
    ItemStudioCredit,
    MediaTypes,
    Movie,
    Sources,
    Status,
    Studio,
)
from app.providers import services
from users.models import ThemeChoices


def _user(name):
    user = get_user_model().objects.create_user(username=name, password="x")
    user.theme = ThemeChoices.CINETRACK
    user.save(update_fields=["theme"])
    return user


class SessionsScreenTests(TestCase):
    """GET /api/v1/history/sessions/ lists what the Django dialog lists."""

    def setUp(self):
        cache.clear()
        for target in (
            "app.models.item.providers.services.get_media_metadata",
            "app.models.media.providers.services.get_media_metadata",
        ):
            patcher = patch(target, return_value={"max_progress": 1})
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("app.models.Item.fetch_releases")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = _user("sessions")
        self.client.force_login(self.user)
        self.base = timezone.now().replace(second=0, microsecond=0)

    def _item(self, media_type, media_id, title):
        return Item.objects.create(
            media_id=media_id,
            source=Sources.MANUAL.value,
            media_type=media_type,
            title=title,
            image="http://example.com/poster.jpg",
            runtime_minutes=42,
        )

    def _django_keys(self, **query):
        response = self.client.get(reverse("activity_sessions_modal"), query)
        self.assertEqual(response.status_code, 200)
        return [
            [entry["entry_key"] for entry in day["entries"]]
            for day in response.context["history_days"]
        ], response.context

    def _api(self, **query):
        response = self.client.get(reverse("api_history_sessions"), query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_movie_book_and_game_are_the_dialogs_days(self):
        movie = self._item(MediaTypes.MOVIE.value, "movie", "Some Movie")
        Movie.objects.create(
            item=movie,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=self.base,
        )
        Movie.objects.create(
            item=movie,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=self.base - timedelta(days=3),
        )
        book = self._item(MediaTypes.BOOK.value, "book", "Some Book")
        Book.objects.create(
            item=book,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=self.base,
        )
        game = self._item(MediaTypes.GAME.value, "game", "Some Game")
        for days in (0, 2):
            Game.objects.create(
                item=game,
                user=self.user,
                status=Status.COMPLETED.value,
                progress=30,
                start_date=self.base - timedelta(days=days, minutes=30),
                end_date=self.base - timedelta(days=days),
            )

        cases = (
            {"media_type": "movie", "media_id": "movie", "source": "manual"},
            {"media_type": "book", "media_id": "book", "source": "manual"},
            {
                "media_type": "game",
                "media_id": "game",
                "source": "manual",
                "logging_style": "sessions",
            },
        )
        for query in cases:
            with self.subTest(query=query):
                keys, context = self._django_keys(**query)
                data = self._api(**query)
                self.assertTrue(keys)
                self.assertEqual(
                    [[entry["key"] for entry in day["entries"]] for day in data["days"]],
                    keys,
                )
                self.assertEqual(
                    [stat["value"] for stat in data["stats"]],
                    [str(stat["value"]) for stat in context["session_history_stats"]],
                )
                self.assertEqual(
                    {"label", "value"}, set(data["stats"][0].keys())
                )
                self.assertFalse(data["capped"])
                self.assertEqual(data["max_days"], 400)

        movie_days = self._api(media_type="movie", media_id="movie", source="manual")["days"]
        self.assertEqual(len(movie_days), 2)
        entry = movie_days[0]["entries"][0]
        self.assertEqual(entry["title"], "Some Movie")
        self.assertEqual(entry["track"]["media_type"], "movie")
        self.assertIsNotNone(entry["track"]["instance_id"])

    def test_another_users_activity_is_not_listed(self):
        other = _user("other")
        movie = self._item(MediaTypes.MOVIE.value, "movie", "Not Yours")
        Movie.objects.create(
            item=movie,
            user=other,
            status=Status.COMPLETED.value,
            end_date=self.base,
        )

        data = self._api(media_type="movie", media_id="movie", source="manual")

        self.assertEqual(data["days"], [])
        self.assertFalse(data["capped"])

    def test_capped_at_the_dialogs_day_limit(self):
        movie = self._item(MediaTypes.MOVIE.value, "movie", "Some Movie")
        for days in range(3):
            Movie.objects.create(
                item=movie,
                user=self.user,
                status=Status.COMPLETED.value,
                end_date=self.base - timedelta(days=days),
            )

        with patch("app.history_views.SESSION_HISTORY_MAX_DAYS", 2):
            data = self._api(media_type="movie", media_id="movie", source="manual")

        self.assertEqual(len(data["days"]), 2)
        self.assertTrue(data["capped"])
        self.assertEqual(data["max_days"], 2)

    def test_requires_a_login(self):
        self.client.logout()
        response = self.client.get(reverse("api_history_sessions"))
        self.assertIn(response.status_code, (401, 403))


@patch("app.providers.services.get_media_metadata", side_effect=_metadata)
class DetailShellOpenersTests(TestCase):
    """The shell's `sessions_query` and `graphs`."""

    def setUp(self):
        cache.clear()
        self.user = _user("openers")
        self.client.force_login(self.user)

    def _shell(self, *args):
        response = self.client.get(reverse("api_detail_shell", args=args))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_book_with_activity_has_a_sessions_query(self, _metadata_mock):
        item = Item.objects.create(
            media_id="OL1W",
            source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value,
            title="Test Book",
            image="https://covers.example/book.jpg",
        )
        Book.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value, progress=120
        )

        shell = self._shell("book", "openlibrary", "OL1W")

        self.assertEqual(
            shell["meta"]["sessions_query"],
            "media_type=book&media_id=OL1W&source=openlibrary",
        )
        self.assertEqual(shell["graphs"], [])

    def test_show_with_a_watched_episode_has_a_sessions_query(self, _metadata_mock):
        from app.models import TV, Episode, Season

        show_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
            image="https://image.tmdb.org/t/p/w500/show.jpg",
        )
        tv = TV.objects.create(
            item=show_item, user=self.user, status=Status.IN_PROGRESS.value
        )
        season_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title="Test Show",
            image="https://image.tmdb.org/t/p/w500/show.jpg",
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
        )
        episode_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=1,
            title="Test Show",
            image="https://image.tmdb.org/t/p/w500/show.jpg",
        )
        Episode.objects.create(
            item=episode_item, related_season=season, end_date=timezone.now()
        )

        shell = self._shell("tv", "tmdb", "1399")

        self.assertEqual(
            shell["meta"]["sessions_query"],
            "media_type=tv&media_id=1399&source=tmdb",
        )
        self.assertTrue(shell["meta"]["percent"])

    def test_untracked_book_has_none(self, _metadata_mock):
        shell = self._shell("book", "openlibrary", "OL1W")

        self.assertIsNone(shell["meta"]["sessions_query"])

    def test_game_sessions_query_logs_by_session(self, _metadata_mock):
        item = Item.objects.create(
            media_id="7",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="Test Game",
            image="https://img.example/game.jpg",
        )
        Game.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value, progress=30
        )

        with patch("app.media_details_views._build_game_lengths_context", return_value={}):
            shell = self._shell("game", "igdb", "7")

        self.assertEqual(
            shell["meta"]["sessions_query"],
            "media_type=game&media_id=7&source=igdb&logging_style=sessions",
        )


@patch("app.providers.services.get_media_metadata", side_effect=_metadata)
class RatingsGraphsTests(TestCase):
    """The shell lists the graph kinds; the endpoint serializes them."""

    def setUp(self):
        cache.clear()
        self.user = _user("graphs")
        self.client.force_login(self.user)

    def _episodes(self, **fields):
        for season, episode, score, votes in (
            (1, 1, 8.8, 1200),
            (1, 2, 7.1, 1),
            (2, 1, 9.4, 15),
        ):
            Item.objects.create(
                media_id="1399",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title="Test Show",
                season_number=season,
                episode_number=episode,
                **{
                    f"{kind}_rating": score
                    for kind in fields.get("kinds", ("provider",))
                },
                **{
                    f"{kind}_rating_count": votes
                    for kind in fields.get("kinds", ("provider",))
                },
            )

    def test_without_stored_ratings_no_graph_is_listed(self, _metadata_mock):
        shell = self.client.get(
            reverse("api_detail_shell", args=("tv", "tmdb", "1399"))
        ).json()

        self.assertEqual(shell["graphs"], [])

    def test_shell_lists_the_kinds_with_data_and_the_endpoint_serializes_them(
        self, _metadata_mock
    ):
        self._episodes(kinds=("provider", "imdb"))

        shell = self.client.get(
            reverse("api_detail_shell", args=("tv", "tmdb", "1399"))
        ).json()
        self.assertEqual(shell["graphs"], ["provider", "imdb"])
        self.assertNotIn("provider_series_graph_data", shell)

        response = self.client.get(
            reverse("api_detail_graphs", args=("tv", "tmdb", "1399"))
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        data = response.json()
        self.assertIsNone(data["trakt"])
        graph = data["provider"]
        self.assertEqual(graph["title"], "Episode Ratings")
        self.assertEqual(graph["row_label"], "E")
        self.assertEqual(
            graph["seasons"],
            [{"label": "S1", "episodes": 2}, {"label": "S2", "episodes": 1}],
        )
        self.assertEqual(
            graph["rows"][0],
            {
                "episode": 1,
                "cells": [
                    {"score": 8.8, "votes": 1200, "color": "#2d9e5f"},
                    {"score": 9.4, "votes": 15, "color": "#1d6e3e"},
                ],
            },
        )
        # Season 2 has no second episode: an empty cell, not a made-up score.
        self.assertEqual(
            graph["rows"][1]["cells"][1], {"score": None, "votes": 0, "color": None}
        )
        self.assertEqual(graph["legend"][0], {"label": "Awesome", "color": "#1d6e3e"})
        self.assertEqual(data["imdb"]["rows"][0]["cells"][0]["score"], 8.8)

    def test_non_series_types_are_400(self, _metadata_mock):
        response = self.client.get(
            reverse("api_detail_graphs", args=("movie", "tmdb", "238"))
        )

        self.assertEqual(response.status_code, 400)


class StudioScreenTests(TestCase):
    """GET /api/v1/details/studio/<source>/<id>/ is the Django studio page."""

    def setUp(self):
        cache.clear()
        for target in (
            "app.models.item.providers.services.get_media_metadata",
            "app.models.media.providers.services.get_media_metadata",
        ):
            patcher = patch(target, return_value={"max_progress": 1})
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("app.models.Item.fetch_releases")
        patcher.start()
        self.addCleanup(patcher.stop)
        self.user = _user("studio")
        self.client.force_login(self.user)
        self.studio = Studio.objects.create(
            source=Sources.IGDB.value,
            source_studio_id="1",
            name="CD Projekt Red",
            logo="https://images.igdb.com/logo123.png",
        )
        self.item = Item.objects.create(
            media_id="1942",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="The Witcher 3",
            image="http://example.com/witcher3.jpg",
            release_datetime=timezone.now(),
        )
        ItemStudioCredit.objects.create(item=self.item, studio=self.studio)

    def _url(self, studio_id="1"):
        return reverse("api_studio_screen", args=("igdb", studio_id))

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_local_credits_with_your_status(self, _profile):
        Game.objects.create(
            item=self.item, user=self.user, status=Status.COMPLETED.value
        )

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200, response.content[:300])
        data = response.json()
        studio = data["studio"]
        self.assertEqual(studio["name"], "CD Projekt Red")
        self.assertTrue(studio["image"].endswith("logo123.png"))
        self.assertEqual(studio["source_label"], "Internet Game Database")
        self.assertEqual(studio["description"], "Studio profile generated from local credits.")
        self.assertIsNone(studio["source_url"])
        self.assertIsNone(studio["founded"])
        self.assertEqual(studio["counts"], [{"label": "Games", "value": 1}])
        (section,) = data["sections"]
        self.assertEqual(section["label"], "Games")
        (card,) = section["cards"]
        self.assertEqual(card["title"], "The Witcher 3")
        self.assertEqual(card["media_type"], "game")
        self.assertEqual(card["status"], "Completed")
        self.assertTrue(card["watched"])
        self.assertIn("/details/igdb/game/1942/", card["url"])

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_studio_without_a_logo_has_no_image(self, _profile):
        Studio.objects.filter(pk=self.studio.pk).update(logo="")

        self.assertIsNone(self.client.get(self._url()).json()["studio"]["image"])

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_another_users_status_is_not_shown(self, _profile):
        Game.objects.create(
            item=self.item, user=_user("other"), status=Status.COMPLETED.value
        )

        card = self.client.get(self._url()).json()["sections"][0]["cards"][0]

        self.assertIsNone(card["status"])
        self.assertFalse(card["watched"])

    @patch(
        "app.providers.igdb.company_profile",
        return_value={
            "description": "Makers of games.",
            "source_url": "https://cdprojektred.example",
            "details": {
                "founded": timezone.now() - timedelta(days=400),
                "developed_count": 3,
                "published_count": 5,
            },
            "games": [],
        },
    )
    def test_provider_profile_adds_the_numbers(self, _profile):
        studio = self.client.get(self._url()).json()["studio"]

        self.assertEqual(studio["description"], "Makers of games.")
        self.assertEqual(studio["source_url"], "https://cdprojektred.example")
        self.assertTrue(studio["founded"])
        self.assertEqual(
            studio["counts"],
            [
                {"label": "Games", "value": 1},
                {"label": "Developed", "value": 3},
                {"label": "Published", "value": 5},
            ],
        )

    @patch("app.providers.igdb.company_profile", return_value=None)
    def test_unknown_studio_is_404(self, _profile):
        self.assertEqual(self.client.get(self._url("999")).status_code, 404)

    @patch(
        "app.providers.igdb.company_profile",
        side_effect=services.ProviderAPIError(Sources.IGDB.value, Exception("down")),
    )
    def test_provider_error_is_503(self, _profile):
        self.assertEqual(self.client.get(self._url()).status_code, 503)
