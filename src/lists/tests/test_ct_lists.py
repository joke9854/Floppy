from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import Item, MediaTypes, Sources
from lists.models import CustomList, CustomListItem
from users.models import ThemeChoices


@override_settings(IMAGE_CACHE_ENABLED=False)
class CineTrackListsPageTests(TestCase):
    """v2 A13: My Lists / Shared with Me, counts and poster-strip covers."""

    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_user(username="lists", password="12345")
        self.friend = User.objects.create_user(username="friend", password="12345")
        self.client.login(username="lists", password="12345")
        self.mine = CustomList.objects.create(name="Mine", owner=self.user)
        self.shared = CustomList.objects.create(name="Theirs", owner=self.friend)
        self.shared.collaborators.add(self.user)

    def _use_cinetrack(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])

    def test_cinetrack_defaults_to_my_lists(self):
        self._use_cinetrack()

        response = self.client.get(reverse("lists"))

        self.assertContains(response, 'class="ct-page-title"')
        self.assertContains(response, "1 list")
        self.assertContains(response, "1 shared with you")
        self.assertContains(response, "ct-lists-scope")
        self.assertEqual([custom_list.name for custom_list in response.context["custom_lists"]], ["Mine"])
        self.assertContains(response, 'class="ct-list-card group"', count=1)

    def test_cinetrack_shared_scope_lists_only_shared(self):
        self._use_cinetrack()

        response = self.client.get(reverse("lists"), {"scope": "shared"})

        self.assertEqual([custom_list.name for custom_list in response.context["custom_lists"]], ["Theirs"])
        self.assertContains(response, "Shared")

    def test_cover_is_a_poster_strip_for_cinetrack(self):
        for index in range(5):
            item = Item.objects.create(
                media_id=str(index),
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Movie {index}",
                image=f"https://image.tmdb.org/t/p/w500/{index}.jpg",
            )
            CustomListItem.objects.create(custom_list=self.mine, item=item)
        url = reverse("list_cover_image", args=[self.mine.id])

        response = self.client.get(url)

        self.assertContains(response, "ct-list-cover")
        self.assertContains(response, "<img", count=4)
        self.assertContains(response, "/w185/0.jpg")
