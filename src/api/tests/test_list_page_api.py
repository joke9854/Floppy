"""A list's page for the web (v2 P4-I2, smart lists P4-I3).

GET /api/v1/lists/page/<reference>/ reads the list page's own context; it
hands read-only visitors and missing lists back to Django. Moving an item
(the page's move buttons) reorders the whole list, so the items beyond the
loaded page keep their order. A smart list carries its saved rules, which
the web posts back whole; recommendations and activity answer JSON for the
page's dialogs.
"""

import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import events.tasks
from app.models import Item, MediaTypes, Movie, Sources, Status
from lists.models import (
    CustomList,
    CustomListItem,
    ListActivity,
    ListActivityType,
    ListRecommendation,
)


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

    def test_recommendations_follow_the_list_settings(self):
        # A private list, or one without recommendations, offers none.
        self.assertFalse(self._page(self.custom_list.id)["list"]["can_recommend"])
        self.custom_list.visibility = "public"
        self.custom_list.save(update_fields=["visibility"])
        self.assertEqual(
            self._page(self.custom_list.id)["list"]["can_recommend"],
            self.custom_list.can_recommend(),
        )

    def test_table_has_cells(self):
        screen = self._page(self.custom_list.id, "?layout=table")
        self.assertEqual(screen["layout"], "table")
        self.assertTrue(screen["columns"])
        self.assertTrue(screen["cards"][0]["cells"])

    def test_read_only_and_missing_lists_go_to_django(self):
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

    def _smart_list(self):
        smart = CustomList.objects.create(
            name="Smart",
            owner=self.user,
            is_smart=True,
            smart_media_types=[MediaTypes.MOVIE.value],
            smart_filters={"status": [Status.COMPLETED.value], "rating": "rated", "search": "Movie"},
        )
        smart.sync_smart_items()
        return smart

    def test_smart_list_carries_its_rules_and_items(self):
        smart = self._smart_list()
        page = self.client.get(reverse("list_detail", args=[smart.id]))
        screen = self._page(smart.id)

        self.assertTrue(screen["handled"])
        self.assertEqual(screen["list"]["items_count"], page.context["items_count"])
        self.assertEqual(screen["list"]["items_count"], 10)
        self.assertEqual(
            [card["key"] for card in screen["cards"]],
            [item.id for item in page.context["items"]],
        )
        rules = screen["smart"]["rules"]
        self.assertEqual(rules["media_types"], [MediaTypes.MOVIE.value])
        self.assertEqual(rules["status"], [Status.COMPLETED.value])
        self.assertEqual(rules["rating"], "rated")
        summary = {chip["label"]: chip["value"] for chip in screen["smart"]["summary"]}
        self.assertEqual(summary["Types:"], "Movie")
        self.assertEqual(summary["Rating:"], "Rated")
        self.assertEqual(summary["Search:"], "\u201cMovie\u201d")
        self.assertEqual(screen["urls"]["add_item"], "")
        self.assertFalse(any(row["value"] == str(smart.id) for row in screen["smart"]["lists"]))

    def test_posting_the_rules_back_changes_nothing(self):
        from lists import smart_rules

        def rules(custom_list):
            # What the rules mean: a save writes every key, with its default.
            return smart_rules.normalize_rule_payload(
                {"media_types": custom_list.smart_media_types, **custom_list.smart_filters},
                custom_list.owner,
            )

        smart = self._smart_list()
        before = (rules(smart), list(smart.smart_media_types), set(smart.items.values_list("id", flat=True)))
        screen = self._page(smart.id)
        response = self.client.post(
            screen["smart"]["save_url"],
            data=json.dumps(screen["smart"]["rules"]),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        smart.refresh_from_db()
        self.assertEqual(rules(smart), before[0])
        self.assertEqual(smart.smart_media_types, before[1])
        self.assertEqual(set(smart.items.values_list("id", flat=True)), before[2])

    def test_recommendations_and_activity_answer_json(self):
        self.custom_list.visibility = "public"
        self.custom_list.allow_recommendations = True
        self.custom_list.save(update_fields=["visibility", "allow_recommendations"])
        extra = Item.objects.create(
            media_id="i3-rec",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Recommended",
        )
        approve = ListRecommendation.objects.create(custom_list=self.custom_list, item=extra, anonymous_name="Kim")
        deny = ListRecommendation.objects.create(custom_list=self.custom_list, item=self.items[0], note="Again")
        json_headers = {"HTTP_ACCEPT": "application/json"}

        listed = self.client.get(reverse("list_recommendations", args=[self.custom_list.id]), **json_headers)
        rows = {row["id"]: row for row in listed.json()["recommendations"]}
        self.assertEqual(rows[approve.id]["recommender"], "Kim")
        self.assertEqual(rows[deny.id]["note"], "Again")

        approved = self.client.post(rows[approve.id]["approve_url"], **json_headers)
        self.assertEqual(approved.json()["added"], True)
        self.assertTrue(self.custom_list.items.filter(id=extra.id).exists())
        denied = self.client.post(rows[deny.id]["deny_url"], **json_headers)
        self.assertTrue(denied.json()["done"])
        self.assertFalse(ListRecommendation.objects.filter(custom_list=self.custom_list).exists())

        activity = self.client.get(reverse("list_activity", args=[self.custom_list.id]), **json_headers)
        types = [row["type"] for row in activity.json()["activities"]]
        self.assertIn(ListActivityType.RECOMMENDATION_APPROVED, types)
        self.assertIn(ListActivityType.RECOMMENDATION_DENIED, types)
        self.assertEqual(
            len(types), ListActivity.objects.filter(custom_list=self.custom_list).count()
        )
        # The pages still answer HTML.
        self.assertEqual(
            self.client.get(reverse("list_activity", args=[self.custom_list.id]))["Content-Type"].split(";")[0],
            "text/html",
        )
