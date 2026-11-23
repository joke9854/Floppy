"""The web Lists index (v2 P4-I1).

GET /api/v1/lists/screen/ reads the Lists page's own context; the list form
views answer JSON for the web dialog. The edit round trip must keep every
field it does not change: the form saves all of them.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Item, MediaTypes, Sources
from lists.models import CustomList, CustomListItem

JSON = {"HTTP_ACCEPT": "application/json"}


class ListsScreenTests(TestCase):
    """The index follows the page."""

    def setUp(self):
        self.credentials = {"username": "i1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.other = get_user_model().objects.create_user(username="i1-friend", password="12345")
        self.client.login(**self.credentials)
        self.mine = CustomList.objects.create(name="Watchlist", owner=self.user)
        self.empty = CustomList.objects.create(name="Empty", owner=self.user)
        self.shared = CustomList.objects.create(name="Their List", owner=self.other)
        self.shared.collaborators.add(self.user)
        for index in range(6):
            item = Item.objects.create(
                media_id=f"i1-{index}",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Movie {index}",
            )
            CustomListItem.objects.create(custom_list=self.mine, item=item, added_by=self.user)

    def _screen(self, query=""):
        response = self.client.get(reverse("api_lists_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_index_follows_the_page(self):
        page = self.client.get(reverse("lists"))
        screen = self._screen()

        self.assertEqual((screen["owned_count"], screen["shared_count"]), (2, 1))
        self.assertEqual(screen["scope"], "mine")
        self.assertEqual(
            [card["name"] for card in screen["cards"]],
            [custom_list.name for custom_list in page.context["custom_lists"]],
        )
        watchlist = next(card for card in screen["cards"] if card["name"] == "Watchlist")
        self.assertEqual(len(watchlist["covers"]), 4)
        self.assertTrue(watchlist["meta"].startswith("6 items · Private"))
        self.assertTrue(watchlist["can_edit"])
        self.assertEqual(screen["urls"]["edit_form"], "/list/{id}/edit-form")

        shared = self._screen("?scope=shared")
        self.assertEqual([card["name"] for card in shared["cards"]], ["Their List"])
        self.assertIn("Shared", shared["cards"][0]["meta"])


class ListFormJsonTests(TestCase):
    """Create, edit and delete answer JSON; an edit keeps what it does not change."""

    def setUp(self):
        self.credentials = {"username": "i1-owner", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.friend = get_user_model().objects.create_user(username="i1-collab", password="12345")
        self.client.login(**self.credentials)
        self.smart = CustomList.objects.create(
            name="Smart Picks",
            owner=self.user,
            is_smart=True,
            visibility="public",
            allow_recommendations=True,
            include_notes=True,
            public_slug="smart-picks",
            tags=["Faves", "Weekend"],
            smart_media_types=["movie"],
            smart_filters={"rating": "rated"},
        )
        self.smart.collaborators.add(self.friend)

    def _form(self, custom_list):
        response = self.client.get(reverse("list_edit_form", args=[custom_list.id]), **JSON)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def _post_back(self, values, **changes):
        """Post every field back as the web dialog does, with `changes`."""
        values = {**values, **changes}
        data = {
            "list_id": values["list_id"],
            "name": values["name"],
            "description": values["description"],
            "tags": values["tags"],
            "collaborator_usernames": [entry["username"] for entry in values["collaborators"]],
            "public_slug": values["public_slug"],
        }
        for flag in ("allow_recommendations", "is_smart", "is_public", "include_notes"):
            if values[flag]:
                data[flag] = "on"
        return self.client.post(reverse("list_edit"), data, **JSON)

    def _assert_kept(self):
        self.smart.refresh_from_db()
        self.assertEqual(self.smart.name, "Renamed")
        self.assertTrue(self.smart.is_smart)
        self.assertEqual(self.smart.visibility, "public")
        self.assertTrue(self.smart.allow_recommendations)
        self.assertTrue(self.smart.include_notes)
        self.assertEqual(self.smart.public_slug, "smart-picks")
        self.assertEqual(sorted(self.smart.tags), ["Faves", "Weekend"])
        self.assertEqual(list(self.smart.collaborators.values_list("username", flat=True)), ["i1-collab"])
        self.assertEqual(self.smart.smart_media_types, ["movie"])
        self.assertEqual(self.smart.smart_filters.get("rating"), "rated")

    def test_rename_keeps_every_other_field(self):
        values = self._form(self.smart)
        self.assertEqual([entry["username"] for entry in values["collaborators"]], ["i1-collab"])
        response = self._post_back(values, name="Renamed")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(response.json()["saved"])
        self._assert_kept()

    def test_collaborator_rename_keeps_every_other_field(self):
        self.client.logout()
        self.client.login(username="i1-collab", password="12345")
        values = self._form(self.smart)
        self.assertFalse(values["can_delete"])
        response = self._post_back(values, name="Renamed")
        self.assertEqual(response.status_code, 200, response.content[:300])
        self._assert_kept()

    def test_edit_errors_and_unknown_collaborators_come_back(self):
        values = self._form(self.smart)
        response = self._post_back(values, public_slug="12345")
        self.assertEqual(response.status_code, 400)
        self.assertIn("public_slug", response.json()["errors"])
        response = self._post_back(values, collaborators=[{"id": 0, "username": "nobody-here"}])
        self.assertEqual(response.status_code, 400)
        self.assertIn("nobody-here", response.json()["errors"]["collaborators"][0])
        self.smart.refresh_from_db()
        self.assertEqual(self.smart.name, "Smart Picks")

    def test_create_and_delete_answer_json(self):
        response = self.client.post(
            reverse("list_create"),
            {"name": "New One", "collaborator_usernames": ["I1-COLLAB"], "is_smart": "on", "smart_create_flow": "1"},
            **JSON,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        body = response.json()
        created = CustomList.objects.get(id=body["list"]["id"])
        self.assertEqual(list(created.collaborators.values_list("username", flat=True)), ["i1-collab"])
        self.assertTrue(body["location"].endswith("?edit_smart_rules=1"))

        response = self.client.post(reverse("list_delete"), {"list_id": created.id}, **JSON)
        self.assertEqual(response.json(), {"deleted": True})
        self.assertFalse(CustomList.objects.filter(id=created.id).exists())
