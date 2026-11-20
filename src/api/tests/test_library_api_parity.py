"""The Library API lists what the Django Library page lists, in the same order (v2 P4-B).

The new web Library reads `GET /api/v1/media/{media_type}/`, whose query
(`app.media_list_filters.get_media_list_entries`) is a separate
implementation from the Django `media_list` view. These tests hold them to
the same result for every status and every sort the page offers.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

import events.tasks  # signal handlers reach events.tasks lazily
from app.models import TV, Item, MediaTypes, Movie, Sources, Status

POSTER = "https://image.tmdb.org/t/p/w500/abc.jpg"

STATUSES = (
    Status.COMPLETED.value,
    Status.IN_PROGRESS.value,
    Status.PLANNING.value,
    Status.PAUSED.value,
    Status.DROPPED.value,
)



class LibraryFixtures(TestCase):
    """Seven shows and seven movies across every status, with scores and dates."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "parity", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        now = timezone.now()
        titles = ["Breaking Bad", "andor", "The Bear", "Zeta", "Alpha", "Mid", "Écho"]
        for index, title in enumerate(titles):
            status = STATUSES[index % len(STATUSES)]
            show = Item.objects.create(
                media_id=str(1000 + index),
                source=Sources.TMDB.value,
                media_type=MediaTypes.TV.value,
                title=title,
                image=POSTER,
                release_datetime=now - timedelta(days=400 * (index % 3) + index),
            )
            TV.objects.create(
                item=show,
                user=self.user,
                status=status,
                score=(index * 3) % 10 or None,
            )
            movie = Item.objects.create(
                media_id=str(2000 + index),
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"{title} Movie",
                image=POSTER,
                release_datetime=now - timedelta(days=90 * ((index * 5) % 7)),
            )
            Movie.objects.create(
                item=movie,
                user=self.user,
                status=status,
                score=(index * 7) % 10 or None,
                start_date=now - timedelta(days=20 - index) if index % 2 else None,
                end_date=now - timedelta(days=(index * 4) % 9)
                if status == Status.COMPLETED.value or index % 3 == 0
                else None,
            )

    def _page_ids(self, media_type, params):
        response = self.client.get(reverse("medialist", args=[media_type]), params)
        self.assertEqual(response.status_code, 200)
        return [entry.item.id for entry in response.context["media_list"]]

    def _api_ids(self, media_type, params):
        response = self.client.get(
            reverse("api_media_type_list", args=[media_type]), {**params, "limit": 100}
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return [entry["id"] for entry in response.json()["results"]]



class LibraryApiParityTests(LibraryFixtures):
    """GET /api/v1/media/{type}/ and /medialist/{type} return the same items."""

    def _assert_same(self, media_type, params):
        page = self._page_ids(media_type, params)
        api = self._api_ids(media_type, params)
        self.assertEqual(api, page, f"{media_type} {params}")

    def _offered_sorts(self, media_type):
        """The sorts the page's menu offers for this type (others fall back to Title)."""
        context = self.client.get(reverse("medialist", args=[media_type])).context
        sorts = [value for value, _label in context["sort_choices"]]
        if not context.get("supports_critic_rating_sort"):
            sorts = [sort for sort in sorts if sort != "critic_rating"]
        if not (context.get("filter_data") or {}).get("show_authors"):
            sorts = [sort for sort in sorts if sort != "author"]
        return sorts

    def test_every_offered_sort_both_ways(self):
        for media_type in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            for sort in self._offered_sorts(media_type):
                for direction in ("asc", "desc"):
                    with self.subTest(media_type=media_type, sort=sort, direction=direction):
                        self._assert_same(media_type, {"sort": sort, "direction": direction})

    def test_each_status(self):
        for media_type in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            for status in STATUSES:
                with self.subTest(media_type=media_type, status=status):
                    self._assert_same(
                        media_type, {"status": status, "sort": "title", "direction": "asc"}
                    )

    def test_search(self):
        for media_type in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            with self.subTest(media_type=media_type):
                self._assert_same(
                    media_type, {"search": "bear", "sort": "title", "direction": "asc"}
                )


class LibraryScreenTests(LibraryFixtures):
    """GET /api/v1/library/{type}/: the page's own list, as cards for the web."""

    def _screen(self, media_type, params=None):
        response = self.client.get(
            reverse("api_library_screen", args=[media_type]), params or {}
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_lists_the_page_exactly(self):
        for media_type in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            for params in (
                {"sort": "time_left", "direction": "asc"},
                {"sort": "start_date", "direction": "desc"},
                {"sort": "score", "direction": "desc"},
                {"status": Status.COMPLETED.value, "sort": "title", "direction": "asc"},
                {"search": "bear", "sort": "title", "direction": "asc"},
            ):
                with self.subTest(media_type=media_type, params=params):
                    page = self._page_ids(media_type, params)
                    screen = [card["key"] for card in self._screen(media_type, params)["results"]]
                    self.assertEqual(screen, page)

    def test_menus_and_cards(self):
        body = self._screen(MediaTypes.MOVIE.value, {"sort": "end_date", "direction": "desc"})

        self.assertEqual(body["count"], 7)
        self.assertEqual(body["sort"], "end_date")
        self.assertEqual(body["direction"], "desc")
        self.assertIn("end_date", [choice["value"] for choice in body["sorts"]])
        self.assertNotIn("time_left", [choice["value"] for choice in body["sorts"]])
        self.assertIn(Status.COMPLETED.value, [c["value"] for c in body["status_choices"]])
        card = body["results"][0]
        self.assertTrue(card["poster"])
        self.assertTrue(card["url"])
        self.assertTrue(card["detail"], "the Last Watched date, as the page shows it")
        self.assertTrue(card["subtitle"], "the status, as the page's card says it")

    def test_filters_list_the_page_exactly(self):
        year = str((timezone.now() - timedelta(days=90)).year)
        for filters in (
            {"rating": "rated"},
            {"rating": "not_rated"},
            {"collection": "not_collected"},
            {"release": "released"},
            {"year": year},
            {"rating": "rated", "year": year},
        ):
            params = {**filters, "status": "all", "sort": "title", "direction": "asc"}
            with self.subTest(params=params):
                page = self._page_ids(MediaTypes.MOVIE.value, params)
                body = self._screen(MediaTypes.MOVIE.value, params)
                self.assertEqual([card["key"] for card in body["results"]], page)
                self.assertEqual(body["count"], len(page))

    def test_filter_menu_state_and_options(self):
        year = str((timezone.now() - timedelta(days=90)).year)
        body = self._screen(MediaTypes.MOVIE.value, {"rating": "rated", "year": year})

        self.assertEqual(body["filters"]["rating"], "rated")
        self.assertEqual(body["filters"]["year"], year)
        self.assertEqual(body["filters"]["collection"], "all")
        self.assertEqual(body["filters"]["tags"], [])
        options = body["filter_options"]
        self.assertIn(year, [option["value"] for option in options["years"]])
        self.assertTrue(options["show_languages"])
        self.assertFalse(options["show_platforms"])
        self.assertFalse(options["show_progress"])
        self.assertTrue(self._screen(MediaTypes.TV.value)["filter_options"]["show_progress"])

    def test_saves_the_sort_like_the_page(self):
        self._screen(MediaTypes.MOVIE.value, {"sort": "score", "direction": "asc"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.movie_sort, "score")
        self.assertEqual(self.user.movie_direction, "asc")

    def _page_table(self, media_type, params):
        """Return the Django table's columns and each row's cell text, in order."""
        from html.parser import HTMLParser

        response = self.client.get(reverse("medialist", args=[media_type]), params)
        keys = [column.key for column in response.context["resolved_columns"]]

        class Cells(HTMLParser):
            def __init__(self):
                super().__init__()
                self.rows, self.depth, self.cell = [], 0, None

            def handle_starttag(self, tag, attrs):
                if tag == "tbody" and dict(attrs).get("id") == "media-table-body":
                    self.depth = 1
                elif self.depth and tag == "tr":
                    self.rows.append([])
                elif self.depth and tag == "td":
                    self.cell = []

            def handle_endtag(self, tag):
                if tag == "td" and self.cell is not None:
                    self.rows[-1].append(" ".join("".join(self.cell).split()))
                    self.cell = None
                elif tag == "tbody":
                    self.depth = 0

            def handle_data(self, data):
                if self.cell is not None:
                    self.cell.append(data)

        parser = Cells()
        parser.feed(response.content.decode())
        # Bulk select and drag columns come first; the resolved columns are the last.
        return keys, [dict(zip(keys, row[-len(keys):], strict=True)) for row in parser.rows]

    def test_table_cells_read_like_the_page(self):
        for media_type in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            params = {"layout": "table", "status": "all", "sort": "title", "direction": "asc"}
            with self.subTest(media_type=media_type):
                keys, rows = self._page_table(media_type, params)
                body = self._screen(media_type, params)

                self.assertEqual(body["layout"], "table")
                self.assertEqual([column["key"] for column in body["columns"]], keys)
                self.assertEqual(len(body["results"]), len(rows))
                for card, row in zip(body["results"], rows, strict=True):
                    for cell in card["cells"]:
                        if cell["items"] or cell["key"] in ("genres", "tags"):
                            continue
                        shown = " ".join(filter(None, [cell["text"], cell["note"]]))
                        expected = row[cell["key"]]
                        self.assertEqual(
                            shown or "-", "-" if expected in ("", "--") else expected, cell["key"]
                        )

    def test_table_lists_tags_and_saves_the_layout(self):
        from app.models import ItemTag, Tag

        movie = Movie.objects.filter(user=self.user).select_related("item").first()
        for name in ("Zed", "Alpha"):
            tag = Tag.objects.create(user=self.user, name=name)
            ItemTag.objects.create(item=movie.item, tag=tag)
        other = get_user_model().objects.create_user(username="other", password="x")
        ItemTag.objects.create(item=movie.item, tag=Tag.objects.create(user=other, name="Theirs"))
        body = self._screen(MediaTypes.MOVIE.value, {"layout": "table", "status": "all"})

        self.user.refresh_from_db()
        self.assertEqual(self.user.movie_layout, "table")
        self.assertTrue(body["column_config"])
        self.assertTrue(body["column_defaults"])
        row = next(card for card in body["results"] if card["key"] == movie.item.id)
        cells = {cell["key"]: cell for cell in row["cells"]}
        self.assertEqual(cells["tags"]["items"], ["Alpha", "Zed"])
        self.assertNotIn("image", cells)
        self.assertNotIn("title", cells)
        grid = self._screen(MediaTypes.MOVIE.value, {"layout": "grid"})
        self.assertEqual(grid["layout"], "grid")
        self.assertEqual(grid["columns"], [])
        self.assertEqual(grid["results"][0]["cells"], [])

    def test_table_reads_no_more_queries_per_row(self):
        def queries(layout):
            self._screen(MediaTypes.MOVIE.value, {"layout": layout, "status": "all"})
            with CaptureQueriesContext(connection) as captured:
                self._screen(MediaTypes.MOVIE.value, {"layout": layout, "status": "all"})
            return len(captured)

        # The tags column reads every row's tags in one query.
        self.assertLessEqual(queries("table") - queries("grid"), 2)

    def test_types_without_a_web_library_yet(self):
        response = self.client.get(reverse("api_library_screen", args=["music"]))

        self.assertEqual(response.status_code, 400)

    def test_integration_tokens_cannot_call_it(self):
        from django.test import Client

        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(
            user=self.user, name="library", scopes=["catalog:read", "progress:read"]
        )
        response = Client().get(
            reverse("api_library_screen", args=["movie"]), HTTP_X_API_KEY=raw
        )

        self.assertEqual(response.status_code, 403)


class EpisodeAirDateSortTests(TestCase):
    """The Library's Episode Air Date sort reads unstarted seasons in one query."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="airdate", password="12345")
        self.client.force_login(self.user)
        self.now = timezone.now()

    def _caught_up_show(self, index, next_season_starts_in_days):
        """Season 1 watched to the end; season 2 not started, with its own air dates."""
        from app.models import Episode, Season
        from events.models import Event

        media_id = f"airdate_{index}"
        show = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title=f"Show {index:02d}",
            image=POSTER,
        )
        TV.objects.create(item=show, user=self.user, status=Status.IN_PROGRESS.value)
        season_one = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title=f"Show {index:02d}",
            image=POSTER,
        )
        season = Season.objects.create(
            item=season_one, user=self.user, status=Status.COMPLETED.value
        )
        for number in (1, 2):
            Event.objects.create(
                item=season_one, content_number=number, datetime=self.now - timedelta(days=30)
            )
            Episode.objects.create(
                item=Item.objects.create(
                    media_id=media_id,
                    source=Sources.TMDB.value,
                    media_type=MediaTypes.EPISODE.value,
                    season_number=1,
                    episode_number=number,
                    title=f"Show {index:02d}",
                    image=POSTER,
                ),
                related_season=season,
                end_date=self.now - timedelta(days=20),
            )
        season_two = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=2,
            title=f"Show {index:02d}",
            image=POSTER,
        )
        Event.objects.create(
            item=season_two,
            content_number=1,
            datetime=self.now + timedelta(days=next_season_starts_in_days),
        )

    def _queries(self):
        cache.clear()
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(
                reverse("medialist", args=["tv"]),
                {"sort": "next_episode_air_date", "direction": "asc"},
            )
        self.assertEqual(response.status_code, 200)
        return len(context.captured_queries), [
            entry.item.title for entry in response.context["media_list"]
        ]

    def test_query_count_does_not_grow_with_shows(self):
        for index, days in ((0, 9), (1, 3)):
            self._caught_up_show(index, days)
        self._queries()  # the first request also saves the sort preference
        few, _ = self._queries()
        for index in range(2, 6):
            self._caught_up_show(index, 20 + index)

        many, titles = self._queries()

        self.assertEqual(many, few)
        # Ordered by when each show's unstarted season 2 begins.
        self.assertEqual(titles[:2], ["Show 01", "Show 00"])

    def test_the_api_orders_like_the_page(self):
        """GET /api/v1/media/tv/ uses the page's Episode Air Date order, ties included."""
        for index, days in ((0, 9), (1, 3), (2, 9), (3, 30)):
            self._caught_up_show(index, days)
        for direction in ("asc", "desc"):
            params = {"sort": "next_episode_air_date", "direction": direction, "status": "all"}
            page = self.client.get(reverse("medialist", args=["tv"]), params)
            api = self.client.get(
                reverse("api_media_type_list", args=["tv"]), {**params, "limit": 100}
            )
            self.assertEqual(
                [entry["id"] for entry in api.json()["results"]],
                [entry.item.id for entry in page.context["media_list"]],
                direction,
            )
