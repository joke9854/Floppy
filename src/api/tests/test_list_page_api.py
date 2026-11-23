"""A manual list's page for the web (v2 P4-I2).

GET /api/v1/lists/page/<reference>/ reads the list page's own context; it
hands smart lists, read-only visitors and missing lists back to Django.
Moving an item (the page's move buttons) reorders the whole list, so the
items beyond the loaded page keep their order.
"""

import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import Item, MediaTypes, Movie, Sources, Status
from lists.models import CustomList, CustomListItem


class ListPageTests(TestCase):
    """The page follows the Django list page."""

    def setUp(self):
        self.credentials = {"username": "i2", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)
        self.custom_list = CustomList.objects.create(name="Twenty", owner=self.user)
        base = timezone.now() - datetime.timedelta(days=30)
        self.items = []
        for index in range(20):
            item = Item.objects.create(
                media_id=f"i2-{index}",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Movie {index:02d}",
            )
            if index % 2 == 0:
                Movie.objects.create(user=self.user, item=item, status=Status.COMPLETED.value, score=7)
            CustomListItem.objects.create(
                custom_list=self.custom_list,
                item=item,
                added_by=self.user,
                date_added=base + datetime.timedelta(minutes=index),
            )
            self.items.append(item)

    def _page(self, reference, query=""):
        response = self.client.get(reverse("api_list_page", args=[reference]) + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_grid_follows_the_page(self):
        query = "?sort=custom&layout=grid"
        page = self.client.get(reverse("list_detail", args=[self.custom_list.id]) + query)
        screen = self._page(self.custom_list.id, query)

        self.assertTrue(screen["handled"])
        self.assertEqual(screen["list"]["items_count"], 20)
        self.assertEqual(screen["list"]["completion_percent"], page.context["completion_percent"])
        self.assertEqual(screen["layout"], "grid")
        self.assertTrue(screen["ordering"])
        self.assertEqual(len(screen["cards"]), 16)
        self.assertTrue(screen["has_next"])
        self.assertEqual([card["key"] for card in screen["cards"]], [item.id for item in page.context["items"]])
        tracked = next(card for card in screen["cards"] if card["key"] == self.items[0].id)
        untracked = next(card for card in screen["cards"] if card["key"] == self.items[1].id)
        self.assertEqual(tracked["status"], Status.COMPLETED.value)
        self.assertIsNone(untracked["status"])
        self.assertIsNotNone(screen["bulk"])
        # The Django page's bulk menus read the same dict (it was a 1-tuple).
        self.assertIsInstance(page.context["bulk_action_data"], dict)
        self.assertTrue(screen["bulk"]["statuses"])

    def test_table_has_cells(self):
        screen = self._page(self.custom_list.id, "?layout=table")
        self.assertEqual(screen["layout"], "table")
        self.assertTrue(screen["columns"])
        self.assertTrue(screen["cards"][0]["cells"])

    def test_smart_read_only_and_missing_lists_go_to_django(self):
        smart = CustomList.objects.create(name="Smart", owner=self.user, is_smart=True)
        self.assertFalse(self._page(smart.id)["handled"])
        other = get_user_model().objects.create_user(username="i2-other", password="12345")
        theirs = CustomList.objects.create(name="Theirs", owner=other, visibility="public")
        screen = self._page(theirs.id)
        self.assertFalse(screen["handled"])
        self.assertEqual(screen["django_url"], reverse("list_detail", args=[theirs.id]))
        self.assertFalse(self._page("999999")["handled"])

    def test_moving_an_item_keeps_the_rest_in_order(self):
        before = list(
            CustomListItem.objects.filter(custom_list=self.custom_list)
            .order_by("date_added", "id")
            .values_list("item_id", flat=True)
        )
        moved = before[3]
        response = self.client.post(
            reverse("list_reorder_item", args=[self.custom_list.id]),
            {"item_id": moved, "action": "first"},
        )
        self.assertEqual(response.status_code, 204)
        after = list(
            CustomListItem.objects.filter(custom_list=self.custom_list)
            .order_by("date_added", "id")
            .values_list("item_id", flat=True)
        )
        self.assertEqual(after[0], moved)
        self.assertEqual(after[1:], [item_id for item_id in before if item_id != moved])
        # Beyond the first page (16), nothing moved.
        self.assertEqual(after[16:], before[16:])
