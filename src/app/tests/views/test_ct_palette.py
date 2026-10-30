from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.models import Item, MediaTypes, Movie, Sources
from users.models import Status, ThemeChoices


class CommandPaletteTests(TestCase):
    """A1: the CineTrack Ctrl/Cmd+K command palette."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="palette-user",
            password="12345",
        )
        self.client.force_login(self.user)
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Godfather",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
        )

    def _get(self, query="", media_type=""):
        return self.client.get(
            reverse("command_palette"),
            {"q": query, "media_type": media_type},
        )

    def test_empty_query_lists_main_pages_without_settings(self):
        response = self._get()

        self.assertContains(response, reverse("home"))
        self.assertContains(response, reverse("medialist", args=["movie"]))
        self.assertNotContains(response, reverse("appearance"))
        self.assertNotContains(response, "Search online for")

    def test_query_matches_pages_and_settings(self):
        response = self._get("appear")

        self.assertContains(response, reverse("appearance"))
        self.assertNotContains(response, reverse("history"))

    def test_query_matches_saved_library_across_types(self):
        response = self._get("godfa", media_type="tv")

        self.assertContains(response, "The Godfather")
        self.assertContains(response, "In your library")
        self.assertContains(response, "/details/")
        self.assertContains(response, "media_type=tv")

    def test_library_only_covers_enabled_media_types(self):
        self.user.movie_enabled = False
        self.user.save(update_fields=["movie_enabled"])

        response = self._get("godfa")

        self.assertNotContains(response, "The Godfather")
        self.assertNotContains(response, reverse("medialist", args=["movie"]))
        self.assertContains(response, "Search online for")

    def test_palette_renders_in_cinetrack_shell_only(self):
        classic = self.client.get(reverse("home"))
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        cinetrack = self.client.get(reverse("home"))

        self.assertNotContains(classic, 'x-data="ctPalette"')
        self.assertContains(cinetrack, 'x-data="ctPalette"')
        self.assertContains(cinetrack, reverse("command_palette"))
