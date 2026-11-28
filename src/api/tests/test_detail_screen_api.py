"""The web detail page API (v2 P4-C1) against the Django movie and show page.

Both are built by the page's own builders, so these tests check the API
says what the page renders: the hero's action, the sections, the episodes.
"""

import copy
import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import TV, Book, ComicIssue, Item, MediaTypes, Movie, Sources, Status
from users.models import ThemeChoices

MOVIE = {
    "media_id": "238",
    "title": "Test Movie",
    "media_type": MediaTypes.MOVIE.value,
    "source": Sources.TMDB.value,
    "image": "https://image.tmdb.org/t/p/w500/poster.jpg",
    "synopsis": "A <b>family</b> saga.",
    "max_progress": 1,
    "genres": ["Crime", "Drama", "Thriller"],
    "details": {
        "release_date": "1972-03-14",
        "runtime": "2h 55m",
        "certification": "R",
        "status": "Released",
    },
    "cast": [{"person_id": "1", "name": "Al Pacino", "role": "Michael Corleone"}],
    "crew": [{"person_id": "2", "name": "Francis Ford Coppola", "role": "Director"}],
    "related": {
        "recommendations": [
            {
                "media_id": "240",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "title": "The Sequel",
                "image": "https://image.tmdb.org/t/p/w500/sequel.jpg",
                "year": 1974,
            }
        ],
    },
}

SHOW = {
    "media_id": "1399",
    "title": "Test Show",
    "media_type": MediaTypes.TV.value,
    "source": Sources.TMDB.value,
    "image": "https://image.tmdb.org/t/p/w500/show.jpg",
    "synopsis": "Houses at war.",
    "max_progress": 4,
    "details": {"seasons": 2, "episodes": 4, "first_air_date": "2011-04-17"},
    "related": {
        "seasons": [
            {
                "media_id": "1399",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.SEASON.value,
                "title": "Test Show",
                "season_number": number,
                "season_title": f"Season {number}",
                "image": f"https://image.tmdb.org/t/p/w500/s{number}.jpg",
                "episode_count": 2,
                "max_progress": 2,
            }
            for number in (1, 2)
        ],
    },
}


BOOK = {
    "media_id": "OL1W",
    "title": "Test Book",
    "media_type": MediaTypes.BOOK.value,
    "source": Sources.OPENLIBRARY.value,
    "image": "https://covers.example/book.jpg",
    "synopsis": "A long book.",
    "max_progress": 300,
    "series_name": "The Cycle",
    "series_position": 2.0,
    "genres": ["Fantasy", "Adventure"],
    "details": {"format": "Hardcover", "number_of_pages": 300, "author": "A. Writer"},
    "authors_full": [{"person_id": "OL9A", "name": "A. Writer"}],
}

GAME = {
    "media_id": "7",
    "title": "Test Game",
    "media_type": MediaTypes.GAME.value,
    "source": Sources.IGDB.value,
    "image": "https://images.example/game.jpg",
    "synopsis": "A game.",
    "max_progress": None,
    "genres": ["RPG"],
    "details": {"format": "Game", "platforms": "PC"},
}

BOARDGAME = {
    "media_id": "13",
    "title": "Test Board Game",
    "media_type": MediaTypes.BOARDGAME.value,
    "source": Sources.BGG.value,
    "image": "https://images.example/board.jpg",
    "synopsis": "A board game.",
    "max_progress": None,
    "genres": [],
    "details": {"players": "2-4"},
}

# How many issues the comic volume fixture has (a test raises it past a page).
_COMIC_ISSUES = [3]


def _comic(issue_count):
    return {
        "media_id": "4050-1",
        "title": "Test Volume",
        "media_type": MediaTypes.COMIC.value,
        "source": Sources.COMICVINE.value,
        "image": "https://images.example/volume.jpg",
        "synopsis": "A volume.",
        "max_progress": issue_count,
        "genres": [],
        "details": {"format": "Comic"},
        "issues": [
            {
                "media_id": f"4000-{number}",
                "source": Sources.COMICVINE.value,
                "media_type": MediaTypes.COMIC_ISSUE.value,
                "title": f"Issue title {number}",
                "issue_number": str(number),
                "image": f"https://images.example/issue{number}.jpg",
                "cover_date": f"2020-01-{number:02d}",
            }
            for number in range(1, issue_count + 1)
        ],
    }


def _season(number):
    return {
        "media_id": "1399",
        "source": Sources.TMDB.value,
        "media_type": MediaTypes.SEASON.value,
        "title": "Test Show",
        "season_number": number,
        "season_title": f"Season {number}",
        "max_progress": 2,
        "details": {"episodes": 2},
        "episodes": [
            {
                "episode_number": episode,
                "air_date": f"201{number}-04-{episode:02d}",
                "image": f"https://image.tmdb.org/t/p/w500/s{number}e{episode}.jpg",
                "name": f"Episode {number}x{episode}",
                "overview": f"Overview {number}x{episode}.",
                "runtime": 55,
            }
            for episode in (1, 2)
        ],
    }


def _metadata(media_type, media_id, source, season_numbers=None, *_args, **_kwargs):
    # A deep copy each call: the page enriches its related lists in place.
    if media_type == MediaTypes.MOVIE.value:
        return copy.deepcopy(MOVIE)
    if media_type == "tv_with_seasons":
        payload = copy.deepcopy(SHOW)
        for number in season_numbers or []:
            payload[f"season/{number}"] = _season(number)
        return payload
    if media_type == MediaTypes.BOOK.value:
        return copy.deepcopy(BOOK)
    if media_type == MediaTypes.GAME.value:
        return copy.deepcopy(GAME)
    if media_type == MediaTypes.BOARDGAME.value:
        return copy.deepcopy(BOARDGAME)
    if media_type == MediaTypes.COMIC.value:
        return _comic(_COMIC_ISSUES[0])
    if media_type == MediaTypes.SEASON.value:
        return _season(season_numbers[0] if season_numbers else 1)
    return copy.deepcopy(SHOW)


@patch("app.providers.services.get_media_metadata", side_effect=_metadata)
class DetailScreenApiTests(TestCase):
    """The API answers with the page's own data."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="detail", password="x"
        )
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self.client.force_login(self.user)

    def _movie_page(self, query=""):
        url = reverse(
            "media_details",
            kwargs={
                "source": "tmdb",
                "media_type": "movie",
                "media_id": "238",
                "title": "x",
            },
        )
        return self.client.get(url + query).content.decode()

    def _api(self, name, *args, **query):
        response = self.client.get(reverse(name, args=args), query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def _movie(self, status, **extra):
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image=MOVIE["image"],
        )
        return Movie.objects.create(item=item, user=self.user, status=status, **extra)

    def test_untracked_movie_offers_mark_as_watched_like_the_page(self, _metadata_mock):
        shell = self._api("api_detail_shell", "movie", "tmdb", "238")

        self.assertEqual(shell["title"], "Test Movie")
        self.assertEqual(shell["action"], {"kind": "mark", "episode": None})
        self.assertIn('id="ct-mark-movie"', self._movie_page())
        self.assertEqual(shell["synopsis"], "A family saga.")
        self.assertEqual(shell["meta"]["genres"], ["Crime", "Drama"])
        self.assertEqual(shell["meta"]["runtime"], "2h 55m")
        self.assertEqual(shell["meta"]["certification"], "R")
        self.assertEqual(shell["meta"]["year"], "1972")
        self.assertEqual(shell["page_url"], "/details/tmdb/movie/238/test-movie")

    def test_watched_movie_lists_its_plays(self, _metadata_mock):
        self._movie(Status.COMPLETED.value, end_date=timezone.now(), score=8)

        shell = self._api("api_detail_shell", "movie", "tmdb", "238")
        sections = self._api("api_detail_sections", "movie", "tmdb", "238")
        page = self._movie_page("?fragment=secondary")

        self.assertEqual(shell["action"]["kind"], "watched")
        self.assertEqual(shell["status"], Status.COMPLETED.value)
        self.assertEqual([play["label"] for play in sections["plays"]], ["Watched"])
        self.assertIn("Your Plays", page)
        self.assertIn(f"Rated {sections['plays'][0]['score']}", page)

    def test_planned_movie_is_not_a_play(self, _metadata_mock):
        self._movie(Status.PLANNING.value)

        shell = self._api("api_detail_shell", "movie", "tmdb", "238")
        sections = self._api("api_detail_sections", "movie", "tmdb", "238")

        self.assertEqual(shell["action"]["kind"], "mark")
        self.assertEqual(sections["plays"], [])
        self.assertNotIn("Your Plays", self._movie_page("?fragment=secondary"))

    def test_sections_are_the_pages(self, _metadata_mock):
        sections = self._api("api_detail_sections", "movie", "tmdb", "238")
        page = self._movie_page("?fragment=secondary")

        self.assertEqual(sections["cast"][0]["role"], "Michael Corleone")
        self.assertEqual(sections["cast"][0]["url"], "/person/tmdb/1/al-pacino")
        self.assertIn("Michael Corleone", page)
        self.assertEqual(
            [card["title"] for card in sections["recommendations"]], ["The Sequel"]
        )
        self.assertEqual(sections["related"], [])
        self.assertIn("The Sequel", page)
        labels = [row["label"] for row in sections["info"]]
        self.assertIn("Certification", labels)
        for label in labels:
            self.assertIn(f"<dt>{label}</dt>", page)
        self.assertEqual(
            sections["sections"],
            ["history", "related", "cast", "recommendations", "details"],
        )

    def test_sections_the_layout_hides_are_left_out(self, _metadata_mock):
        self.user.detail_page_layouts = {
            "media": {"content": ["recommendations"], "sidebar": ["details"]}
        }
        self.user.save(update_fields=["detail_page_layouts"])

        sections = self._api("api_detail_sections", "movie", "tmdb", "238")

        self.assertEqual(sections["sections"], ["recommendations", "details"])
        self.assertIn(
            'data-detail-section="cast" hidden', self._movie_page("?fragment=secondary")
        )

    def test_show_names_its_next_episode_and_lists_the_season(self, _metadata_mock):
        from app.models import Episode, Season
        from events.models import Event

        show_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
            image=SHOW["image"],
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
            image=SHOW["image"],
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
            image=SHOW["image"],
        )
        Episode.objects.create(
            item=episode_item, related_season=season, end_date=timezone.now()
        )
        for number in (1, 2):
            Event.objects.create(
                item=season_item,
                content_number=number,
                datetime=timezone.now() - timedelta(days=30 - number),
            )

        shell = self._api("api_detail_shell", "tv", "tmdb", "1399")
        sections = self._api("api_detail_sections", "tv", "tmdb", "1399")
        season_two = self._api("api_detail_season", "tmdb", "1399", season=2)
        self.assertEqual(season_two["info"]["title"], "Season 2")
        self.assertEqual(season_two["info"]["episodes"], 2)

        page = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": "tmdb",
                    "media_type": "tv",
                    "media_id": "1399",
                    "title": "x",
                },
            )
        ).content.decode()
        hero = re.search(r'id="ct-mark-next"[^>]*>', page).group(0)
        episode = shell["action"]["episode"]
        self.assertEqual(shell["action"]["kind"], "episode")
        self.assertIn(f'data-season-number="{episode["season_number"]}"', hero)
        self.assertIn(f'data-episode-number="{episode["episode_number"]}"', hero)
        self.assertEqual((episode["season_number"], episode["episode_number"]), (1, 2))
        self.assertEqual(
            [cover["short"] for cover in sections["seasons"]], ["S1", "S2"]
        )
        self.assertTrue(sections["seasons"][0]["current"])
        rows = sections["season"]["episodes"]
        self.assertEqual([row["title"] for row in rows], ["Episode 1x1", "Episode 1x2"])
        self.assertTrue(rows[0]["watched"])
        self.assertTrue(rows[1]["is_next"])
        self.assertEqual(sections["season"]["progress"]["watched"], 1)
        self.assertEqual(
            [row["title"] for row in season_two["episodes"]],
            ["Episode 2x1", "Episode 2x2"],
        )

        fragment = self.client.get(
            reverse(
                "season_details",
                kwargs={
                    "source": "tmdb",
                    "media_id": "1399",
                    "title": "test-show",
                    "season_number": 1,
                },
            ),
            {"fragment": "secondary"},
        ).content.decode()
        for row in rows:
            self.assertIn(row["title"], fragment)

    def test_crew_links_and_fanart(self, _metadata_mock):
        shell = self._api("api_detail_shell", "movie", "tmdb", "238")
        sections = self._api("api_detail_sections", "movie", "tmdb", "238")

        self.assertIsNone(shell["logo"])
        self.assertIsNone(shell["fanart_poster"])
        self.assertIsInstance(shell["links"], list)
        self.assertEqual(sections["crew"][0]["role"], "Director")
        self.assertIn("Francis Ford Coppola", self._movie_page("?fragment=secondary"))
        self.assertIsNone(sections["cast"][0]["character_image"])

    def test_trailers_are_the_pages(self, _metadata_mock):
        videos = [
            {"key": "abc123", "name": "Official Trailer", "type": "Trailer"},
            {"key": "def456", "name": "", "type": "Teaser"},
        ]
        with patch("app.providers.tmdb.carousel_media", return_value={"videos": videos}):
            body = self._api("api_detail_trailers", "movie", "tmdb", "238")

        self.assertEqual(
            body["trailers"],
            [
                {"key": "abc123", "name": "Official Trailer", "type": "Trailer", "season": None},
                {"key": "def456", "name": "Teaser", "type": "Teaser", "season": None},
            ],
        )

    def test_movie_has_none_of_the_l1_fields(self, _metadata_mock):
        shell = self._api("api_detail_shell", "movie", "tmdb", "238")
        sections = self._api("api_detail_sections", "movie", "tmdb", "238")

        self.assertIsNone(shell["meta"]["progress"])
        self.assertIsNone(shell["meta"]["series"])
        self.assertEqual(sections["issues"], [])
        self.assertIsNone(sections["issues_more"])
        self.assertIsNone(sections["game_lengths"])
        self.assertEqual(sections["authors"], [])
        self.assertEqual(sections["studios"], [])
        self.assertEqual(sections["genres"], [])

    def test_book_has_series_progress_authors_and_genres(self, _metadata_mock):
        item = Item.objects.create(
            media_id="OL1W",
            source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value,
            title="Test Book",
            image=BOOK["image"],
        )
        Book.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value, progress=120
        )

        shell = self._api("api_detail_shell", "book", "openlibrary", "OL1W")
        sections = self._api("api_detail_sections", "book", "openlibrary", "OL1W")

        self.assertIsNone(shell["action"])
        self.assertEqual(shell["meta"]["series"], "The Cycle #2")
        self.assertEqual(shell["meta"]["progress"], "Progress: 120/300")
        labels = [row["label"] for row in sections["info"]]
        self.assertIn("Format", labels)
        self.assertNotIn("Author", labels)
        self.assertEqual(
            sections["authors"],
            [{"name": "A. Writer", "url": "/person/openlibrary/OL9A/a-writer"}],
        )
        self.assertEqual(
            [genre["name"] for genre in sections["genres"]], ["Fantasy", "Adventure"]
        )
        self.assertTrue(sections["genres"][0]["url"].endswith("?genre=Fantasy"))
        self.assertIn("genres", sections["sections"])
        self.assertEqual(sections["issues"], [])

    @patch(
        "app.media_details_views._build_game_lengths_context",
        return_value={
            "available": True,
            "source": "igdb",
            "source_label": "Internet Games Database",
            "source_url": None,
            "cards": [
                {
                    "label": "Normally",
                    "value": "12h",
                    "count": 5,
                    "icon_template": "app/icons/clock.svg",
                }
            ],
        },
    )
    def test_game_has_time_to_beat_and_no_action(self, _lengths, _metadata_mock):
        shell = self._api("api_detail_shell", "game", "igdb", "7")
        sections = self._api("api_detail_sections", "game", "igdb", "7")

        self.assertIsNone(shell["action"])
        lengths = sections["game_lengths"]
        self.assertTrue(lengths["available"])
        self.assertEqual(lengths["source_label"], "Internet Games Database")
        self.assertEqual(
            lengths["cards"], [{"label": "Normally", "value": "12h", "count": 5}]
        )
        self.assertIn("game_lengths", sections["sections"])

    @patch("app.media_details_views._should_queue_game_lengths_refresh", return_value=False)
    @patch("app.media_details_views._build_game_lengths_context", return_value=None)
    def test_game_without_figures_says_not_available(self, _lengths, _queue, _metadata_mock):
        sections = self._api("api_detail_sections", "game", "igdb", "7")

        self.assertEqual(
            sections["game_lengths"],
            {
                "available": False,
                "pending": False,
                "source_label": "",
                "source_url": None,
                "cards": [],
            },
        )

    def test_boardgame_renders_without_an_action(self, _metadata_mock):
        shell = self._api("api_detail_shell", "boardgame", "bgg", "13")
        sections = self._api("api_detail_sections", "boardgame", "bgg", "13")

        self.assertIsNone(shell["action"])
        self.assertEqual(shell["title"], "Test Board Game")
        self.assertIsNone(sections["game_lengths"])

    def test_comic_lists_its_issues_with_read_flags_and_pages(self, _metadata_mock):
        _COMIC_ISSUES[0] = 26
        self.addCleanup(_COMIC_ISSUES.__setitem__, 0, 3)
        issue = Item.objects.create(
            media_id="4000-1",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC_ISSUE.value,
            title="Issue title 1",
            image="https://images.example/issue1.jpg",
        )
        ComicIssue.objects.create(
            item=issue, user=self.user, status=Status.COMPLETED.value
        )

        shell = self._api("api_detail_shell", "comic", "comicvine", "4050-1")
        first = self._api("api_detail_sections", "comic", "comicvine", "4050-1")
        second = self._api(
            "api_detail_sections", "comic", "comicvine", "4050-1", episode_page=2
        )

        self.assertIsNone(shell["action"])
        self.assertEqual(len(first["issues"]), 25)
        self.assertEqual(first["issues"][0]["number"], "1")
        self.assertTrue(first["issues"][0]["read"])
        self.assertFalse(first["issues"][1]["read"])
        self.assertEqual(first["issues"][0]["media_type"], "comicissue")
        self.assertEqual(first["issues"][0]["media_id"], "4000-1")
        self.assertEqual(
            first["issues"][0]["url"],
            "/details/comicvine/comicissue/4000-1/issue-title-1",
        )
        self.assertEqual(first["issues_more"]["page"], 2)
        self.assertEqual([i["number"] for i in second["issues"]], ["26"])
        self.assertIsNone(second["issues_more"])

    def test_types_without_a_web_page_yet(self, _metadata_mock):
        response = self.client.get(
            reverse("api_detail_shell", args=["anime", "mal", "1"])
        )

        self.assertEqual(response.status_code, 400)

    def test_integration_tokens_cannot_call_it(self, _metadata_mock):
        from integrations.models import IntegrationToken

        _, raw = IntegrationToken.generate(
            user=self.user, name="detail", scopes=["catalog:read", "progress:read"]
        )
        for name, args in (
            ("api_detail_shell", ["movie", "tmdb", "238"]),
            ("api_detail_sections", ["movie", "tmdb", "238"]),
            ("api_detail_season", ["tmdb", "1399"]),
            ("api_detail_trailers", ["movie", "tmdb", "238"]),
        ):
            response = Client().get(reverse(name, args=args), HTTP_X_API_KEY=raw)
            self.assertEqual(response.status_code, 403, name)
