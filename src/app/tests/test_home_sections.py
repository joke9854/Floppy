from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app import home_sections
from app.cache_utils import clear_home_row_cache_for_user
from app.models import Episode, Item, MediaTypes, Movie, Season, Sources, Status
from events.models import Event
from users.models import ThemeChoices

POSTER = "https://image.tmdb.org/t/p/w500/abc.jpg"


class HomeSectionsTests(TestCase):
    """v2 Home: Airing This Week, Recently Watched and the catch-up count."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "sections", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.now = timezone.now()

        self.season_item = self._season_item(1)
        self.season = Season.objects.create(
            item=self.season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        # Eight aired episodes, four watched: four to catch up on.
        for number in range(1, 9):
            Event.objects.create(
                item=self.season_item,
                content_number=number,
                datetime=self.now - timedelta(days=30 - number),
            )
        for number in range(1, 5):
            Episode.objects.create(
                item=self._episode_item(number),
                related_season=self.season,
                end_date=self.now - timedelta(days=10 - number),
            )

    def _season_item(self, season_number):
        return Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=season_number,
            title="Friends",
            image=POSTER,
        )

    def _episode_item(self, number):
        return Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=number,
            title="Friends",
            image=POSTER,
        )

    def _airing(self, sections):
        return [entry for column in sections["airing"] for entry in column]

    def test_catch_up_counts_aired_unwatched_episodes(self):
        sections = home_sections.build_home_sections(self.user)

        self.assertEqual(sections["catch_up"], 4)

    def test_airing_this_week_tags_premiere_and_finale(self):
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )
        Event.objects.create(
            item=self.season_item,
            content_number=10,
            datetime=self.now + timedelta(days=2),
        )
        next_season = self._season_item(2)
        Season.objects.create(
            item=next_season,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=next_season,
            content_number=1,
            datetime=self.now + timedelta(days=3),
        )
        Event.objects.create(
            item=next_season,
            content_number=2,
            datetime=self.now + timedelta(days=30),
        )

        sections = home_sections.build_home_sections(self.user)

        tags = {
            (entry.event.item.season_number, entry.event.content_number): entry.tag
            for entry in self._airing(sections)
        }
        self.assertEqual(tags, {(1, 9): None, (1, 10): "finale", (2, 1): "premiere"})
        self.assertEqual(sections["airing_count"], 3)

    def test_recently_watched_lists_each_title_once_newest_first(self):
        movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image=POSTER,
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            end_date=self.now - timedelta(days=1),
        )

        sections = home_sections.build_home_sections(self.user)

        titles = [entry.item.title for entry in sections["recent"]]
        self.assertEqual(titles, ["Fight Club", "Friends"])

    def test_sections_are_cached_and_cleared_with_the_home_rows(self):
        home_sections.build_home_sections(self.user)
        with patch.object(home_sections, "_catch_up_count") as count:
            home_sections.build_home_sections(self.user)
            count.assert_not_called()

            clear_home_row_cache_for_user(self.user.id)
            count.return_value = 0
            home_sections.build_home_sections(self.user)
            count.assert_called_once()

    def test_cinetrack_home_renders_the_sections(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        Event.objects.create(
            item=self.season_item,
            content_number=9,
            datetime=self.now + timedelta(days=1),
        )

        home = self.client.get(reverse("home")).content.decode()
        rest = self.client.get(reverse("home_rest_fragment")).content.decode()

        self.assertIn("4 episodes to catch up on", home)
        self.assertIn("1 airing this week", home)
        self.assertIn("Airing This Week", rest)
        self.assertIn("Recently Watched", rest)
        self.assertIn(f'href="{reverse("calendar")}"', rest)
        self.assertIn(f'href="{reverse("history")}"', rest)

    def test_classic_home_has_no_sections(self):
        self.user.theme = ThemeChoices.DARK
        self.user.save(update_fields=["theme"])

        home = self.client.get(reverse("home")).content.decode()
        rest = self.client.get(reverse("home_rest_fragment")).content.decode()

        self.assertNotIn("ct-page-sub", home)
        self.assertNotIn("Recently Watched", rest)
