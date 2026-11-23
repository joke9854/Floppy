"""The web Statistics screen (v2 P4-H1).

GET /api/v1/statistics/screen/ reads the Statistics page's own context; these
tests hold its range, summaries, highlights and controls to the page's.
"""

import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import Item, MediaTypes, Movie, Sources, Status


@patch("app.providers.services.get_media_metadata", side_effect=RuntimeError("no network"))
class StatisticsScreenTests(TestCase):
    """The screen follows the page."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "h1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        now = timezone.now()
        for index, title in enumerate(("Seed One", "Seed Two", "Seed Three")):
            item = Item.objects.create(
                media_id=f"h1-{index}",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=title,
                runtime_minutes=100,
            )
            watched = now - datetime.timedelta(days=3 + index * 10)
            Movie.objects.create(
                user=self.user,
                item=item,
                status=Status.COMPLETED.value,
                score=7 + index,
                start_date=watched - datetime.timedelta(hours=2),
                end_date=watched,
            )

    def _screen(self, query=""):
        response = self.client.get(reverse("api_statistics_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_all_time_follows_the_page(self, _metadata):
        query = "?start-date=all&end-date=all"
        page = self.client.get(reverse("statistics") + query)
        screen = self._screen(query)

        self.assertFalse(screen["database_error"])
        self.assertEqual(screen["range"]["name"], "All Time")
        self.assertFalse(screen["range"]["finite"])
        self.assertEqual(screen["compare"]["mode"], "none")
        page_all = page.context["summary_stats_by_type"]["all"]
        self.assertEqual(screen["summaries"]["all"]["completed"], page_all["completed"])
        self.assertEqual(screen["summaries"]["all"]["total"], page_all["total"])
        self.assertEqual(screen["summaries"]["movie"]["has_score"], True)
        self.assertEqual(screen["highlights"]["all"]["last_play"]["title"], "Seed One")
        self.assertTrue(screen["highlights"]["all"]["last_play"]["caption"].startswith("Played "))
        values = [option["value"] for option in screen["media_types"]]
        self.assertEqual(values[:4], ["all", "tv", "movie", "anime"])
        self.assertEqual(
            [preset["name"] for preset in screen["ranges"]][-1],
            "All Time",
        )
        self.assertEqual(screen["ranges"][-1]["dates"], "All activity")
        self.assertEqual(screen["urls"]["refresh"], reverse("refresh_statistics"))
        self.assertEqual(screen["rating_scale_max"], 10)

    def test_charts_follow_the_page(self, _metadata):
        query = "?start-date=all&end-date=all"
        page = self.client.get(reverse("statistics") + query)
        charts = self._screen(query)["charts"]

        self.assertEqual(len(charts["rhythm"]["all"]), 7)
        self.assertEqual(len(charts["rhythm"]["all"][0]), 24)
        self.assertEqual(sum(map(sum, charts["rhythm"]["movie"])), sum(map(sum, page.context["weekday_hour_chart_data"]["movie"])))
        self.assertEqual(charts["hours_by_type"]["labels"], list(page.context["media_type_distribution"]["labels"]))
        self.assertEqual(charts["status"]["labels"], list(page.context["status_distribution"]["labels"]))
        self.assertEqual(
            [series["label"] for series in charts["ratings"]["series"]],
            [dataset["label"] for dataset in page.context["score_distribution"]["datasets"]],
        )
        self.assertTrue(charts["consumption"]["movie"]["has_data"])
        self.assertIn("all", charts["combined"]["by_month"])

    def test_overviews_follow_the_page(self, _metadata):
        screen = self._screen("?start-date=all&end-date=all")

        movie = next(overview for overview in screen["overviews"] if overview["media_type"] == "movie")
        self.assertEqual(movie["eyebrow"], "Movies")
        self.assertEqual([chart["title"] for chart in movie["charts"]], ["Movie Plays by Year"])
        most_played = next(entry for entry in movie["lists"] if entry["title"] == "Most Played")
        self.assertEqual(len(most_played["items"]), 3)
        self.assertIn(" plays" if "plays" in most_played["items"][0]["caption"] else " play", most_played["items"][0]["caption"])
        top_rated = next(entry for entry in movie["lists"] if entry["title"] == "Top Rated")
        self.assertTrue(top_rated["items"])
        # Types without plays have no overview, as on the page.
        self.assertNotIn("tv", [overview["media_type"] for overview in screen["overviews"]])
        self.assertFalse(screen["no_top_played"])

    def test_talent_section_answers_for_the_range(self, _metadata):
        response = self.client.get(
            reverse("api_statistics_talent") + "?range_name=All+Time&start-date=all&end-date=all&media_type=movie"
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        talent = response.json()
        self.assertEqual(talent["talent_sort"], "plays")
        self.assertEqual(talent["urls"]["talent_sort"], reverse("update_top_talent_sort"))
        self.assertIn("role_leaders", talent)
        # Manual titles carry no credits: no featured player, and no error.
        self.assertIsNone(talent["featured"])

    def test_a_finite_range_offers_its_comparisons(self, _metadata):
        # A custom range no preset matches, so the test holds on any date.
        today = timezone.localdate()
        start = (today - datetime.timedelta(days=40)).isoformat()
        end = today - datetime.timedelta(days=5)
        screen = self._screen(f"?start-date={start}&end-date={end.isoformat()}&compare=previous_period")

        self.assertTrue(screen["range"]["finite"])
        self.assertEqual(screen["range"]["name"], "")
        self.assertFalse(screen["range"]["predefined"])
        self.assertEqual(screen["compare"]["mode"], "previous_period")
        options = {option["value"]: option for option in screen["compare"]["options"]}
        self.assertTrue(options["previous_period"]["dates"])
        self.assertTrue(options["last_year"]["dates"])
        self.assertEqual(options["none"]["dates"], "")
        self.assertEqual(screen["range"]["last_day"], end.isoformat())
        self.assertIn("state", screen["activity"])

    @patch("app.statistics_views.statistics_cache.get_statistics_data", side_effect=OperationalError("locked"))
    def test_a_database_error_is_an_error_state(self, _stats, _metadata):
        screen = self._screen("?start-date=all&end-date=all")

        self.assertTrue(screen["database_error"])
        self.assertEqual(screen["summaries"], {})


class StatisticsOverviewShapeTests(TestCase):
    """Every overview branch reads the aggregator's shapes (no local data needed)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="h3-shapes", password="12345")
        for flag in ("music_enabled", "podcast_enabled", "book_enabled", "comic_enabled", "manga_enabled"):
            setattr(self.user, flag, True)
        self.item = Item.objects.create(
            media_id="h3-game",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.GAME.value,
            title="Seed Game",
            image="https://image.tmdb.org/t/p/w342/none.jpg",
        )

    def _media(self):
        from types import SimpleNamespace

        return SimpleNamespace(item=self.item, user=self.user, score=8, aggregated_score=None)

    def _chart(self):
        return {"labels": ["2025", "2026"], "datasets": [{"label": "x", "data": [1, 2], "background_color": "#fff"}]}

    def test_every_branch_builds(self):
        from api.statistics_overviews import build_board_games, build_overviews

        dot = chr(0xB7)
        reading = {
            "has_data": True,
            "unit_name": "Page",
            "completion_label": "Books Finished",
            "completion_charts": {"by_year": self._chart()},
            "release_chart": self._chart(),
            "completed_length_chart": {"labels": [], "datasets": []},
            "top_items": [{"media": self._media(), "formatted_units": "140 pages", "entry_count": 2}],
            "top_authors": [
                {
                    "name": "Ann Author",
                    "image": "",
                    "source": "openlibrary",
                    "person_id": "OL1A",
                    "titles": {1, 2},
                    "formatted_units": "300 pages",
                },
            ],
            "top_genres": [{"name": "Sci-Fi & Fantasy", "formatted_units": "300 pages", "titles": 2}],
        }
        context = {
            "show_year_charts": True,
            "start_date_str": "2026-01-01",
            "end_date_str": "2026-11-23",
            "top_played": {
                "game": [{"media": self._media(), "formatted_duration": "3h 35min", "play_count": 1}],
                "boardgame": [{"media": self._media(), "formatted_duration": "2h"}],
            },
            "game_consumption": {
                "has_data": True,
                "charts": {"by_year": self._chart(), "by_month": self._chart(), "by_daily_average": self._chart()},
                "platform_breakdown": [{"name": "PC", "games": 2, "hours": 3.5, "formatted_hours": "3h 30min"}],
            },
            "music_consumption": {
                "has_data": True,
                "charts": {"by_year": self._chart()},
                "top_artists": [
                    {"name": "Artist", "image": "", "id": 1, "minutes": 60, "plays": 3, "formatted_duration": "1h"},
                ],
                "top_albums": [
                    {
                        "title": "Album",
                        "artist": "Artist",
                        "artist_id": 1,
                        "artist_name": "Artist",
                        "image": "",
                        "id": 2,
                        "plays": 3,
                        "formatted_duration": "1h",
                    },
                ],
                "top_tracks": [
                    {
                        "title": "Track",
                        "album": "Album",
                        "album_image": "",
                        "album_id": 2,
                        "album_artist_id": 1,
                        "album_artist_name": "Artist",
                        "id": 3,
                        "plays": 1,
                        "formatted_duration": "4min",
                    },
                ],
                "top_decades": [{"label": "1990s", "plays": 2, "formatted_duration": "8min"}],
                "top_countries": [{"code": "GB", "name": "United Kingdom", "plays": 2, "formatted_duration": "8min"}],
            },
            "podcast_consumption": {
                "has_data": True,
                "charts": {"by_year": self._chart()},
                "most_played": [
                    {"title": "Show", "show_id": None, "podcast_uuid": "abc", "slug": "show", "image": "", "plays": 4, "formatted_duration": "2h"},
                ],
                "most_listened": [
                    {"title": "Show", "show_id": 7, "podcast_uuid": None, "slug": "", "image": "", "plays": 4, "formatted_duration": "2h"},
                ],
                "longest_episodes": [
                    {"title": "Long One", "show_id": None, "podcast_uuid": None, "image": "", "formatted_duration": "3h"},
                ],
            },
            "book_consumption": reading,
            "comic_consumption": {**reading, "completion_label": "Comics Finished"},
            "manga_consumption": {**reading, "completion_label": "Manga Finished"},
        }

        overviews = build_overviews(context, self.user)

        self.assertEqual(
            [overview["media_type"] for overview in overviews],
            ["manga", "game", "book", "comic", "music", "podcast"],
        )
        by_type = {overview["media_type"]: overview for overview in overviews}
        self.assertEqual(
            [chart["title"] for chart in by_type["game"]["charts"]][1:],
            ["Game Hours by Month", "Average Daily Playtime"],
        )
        self.assertEqual(by_type["game"]["lists"][1]["items"][0]["caption"], f"3h 30min {dot} 2 games")
        self.assertEqual(by_type["music"]["lists"][0]["title"], "Top 1 Artists")
        self.assertTrue(by_type["music"]["lists"][2]["items"][0]["href"])
        self.assertIn("/details/pocketcasts/podcast/abc", by_type["podcast"]["lists"][0]["items"][0]["href"])
        book_lists = {entry["title"]: entry for entry in by_type["book"]["lists"]}
        self.assertEqual(book_lists["Top 1 Authors"]["items"][0]["caption"], f"300 pages {dot} 2 books")
        genre_href = book_lists["Top Genres"]["items"][0]["href"]
        self.assertIn("genre=Sci-Fi+%26+Fantasy", genre_href)
        self.assertIn("start-date=2026-01-01", genre_href)
        self.assertEqual(book_lists["Most Read"]["items"][0]["image"], "")
        self.assertEqual(build_board_games(context)[0]["title"], "Seed Game")
