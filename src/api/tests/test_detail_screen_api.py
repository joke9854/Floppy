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
from app.models import TV, Item, MediaTypes, Movie, Sources, Status
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
