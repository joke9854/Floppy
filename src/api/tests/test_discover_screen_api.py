"""The web Discover screen (v2 P4-G).

GET /api/v1/discover/screen/ reads the Discover page's own context; these
tests hold its rows, hero and Hidden view to the page's, and the JSON answers
discover_action gives the screen's quick actions.
"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.discover.schemas import CandidateItem, RowResult
from app.models import (
    DiscoverFeedback,
    DiscoverFeedbackType,
    Item,
    MediaTypes,
    Sources,
)
from app.services.tracking_hydration import HydratedItemResult

JSON = {"HTTP_ACCEPT": "application/json"}


def _row(key="top_picks_for_you", title="Top Picks For You", items=None):
    if items is None:
        items = [
            CandidateItem(
                media_type="movie",
                source="tmdb",
                media_id="603",
                title="The Matrix",
                image="https://image.tmdb.org/t/p/w500/matrix.jpg",
                release_date="1999-03-31",
                genres=["Action"],
            ),
        ]
    return RowResult(
        key=key,
        title=title,
        mission="Mission",
        why="Why",
        source="local",
        items=items,
    )


@patch("app.middleware.discover_tab_cache.maybe_schedule_user_warmup", return_value=0)
@patch("app.views.discover_tab_cache.warm_sibling_tabs")
@patch("app.views.discover_tab_cache.get_tab_status", return_value={"is_refreshing": False})
class DiscoverScreenTests(TestCase):
    """The screen follows the page's rows, hero and Hidden view."""

    def setUp(self):
        cache.clear()
        self.credentials = {"username": "g1", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _screen(self, query=""):
        response = self.client.get(reverse("api_discover_screen") + query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    @patch("app.templatetags.app_tags.backdrops.resolve_backdrop", return_value="https://image.tmdb.org/t/p/w1280/b.jpg")
    @patch("app.views.discover_tab_cache.get_tab_rows")
    def test_rows_and_hero_follow_the_page(self, mock_rows, _backdrop, *_):
        mock_rows.return_value = [_row(), _row(key="coming_soon", title="Coming Soon", items=[])]
        page = self.client.get(reverse("discover") + "?media_type=movie")
        screen = self._screen("?media_type=movie")

        self.assertEqual(screen["media_type"], "movie")
        self.assertEqual([r["title"] for r in screen["rows"]], [r.title for r in page.context["rows"]])
        card = screen["rows"][0]["cards"][0]
        self.assertEqual(card["title"], "The Matrix")
        self.assertEqual(card["sub"], "Movie · 1999")
        self.assertIn("/details/tmdb/movie/603/", card["href"])
        # The action posts the stored image, not the cache URL: a Hide seeds an Item.
        self.assertEqual(card["action"]["image"], "https://image.tmdb.org/t/p/w500/matrix.jpg")
        self.assertEqual(card["action"]["row_key"], "top_picks_for_you")
        self.assertEqual(card["action"]["active_media_type"], "movie")
        self.assertEqual(screen["rows"][1]["cards"], [])
        self.assertEqual(screen["rows"][1]["empty_message"], "No items matched this row right now.")

        slide = screen["hero"][0]
        self.assertEqual(slide["meta"], "Movie · Action · 1999")
        self.assertEqual(slide["action"]["row_key"], "")
        self.assertTrue(slide["backdrop"])

        values = [option["value"] for option in screen["options"]]
        self.assertEqual(values[0], "all")
        self.assertEqual(screen["options"][0]["label"], "All")
        self.assertNotIn("hidden", values)
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_discover_type, "movie")

    def test_hidden_view_lists_hidden_items(self, *_):
        item = Item.objects.create(
            media_id="11",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Star Wars",
            image="https://image.tmdb.org/t/p/w500/sw.jpg",
        )
        DiscoverFeedback.objects.create(
            user=self.user,
            item=item,
            feedback_type=DiscoverFeedbackType.NOT_INTERESTED.value,
        )
        screen = self._screen("?media_type=hidden")

        self.assertEqual(screen["media_type"], "hidden")
        self.assertEqual(screen["rows"], [])
        self.assertEqual(screen["hidden_count"], 1)
        self.assertTrue(screen["hidden_summary"].startswith("1 item · "))
        hidden = screen["hidden"][0]
        self.assertEqual((hidden["item_id"], hidden["title"]), (item.id, "Star Wars"))
        self.assertTrue(hidden["meta"].startswith("Movie · Hidden "))


@patch("app.middleware.discover_tab_cache.maybe_schedule_user_warmup", return_value=0)
class DiscoverActionJsonTests(TestCase):
    """discover_action answers JSON for the web screen, HTMX keeps the fragment."""

    def setUp(self):
        self.credentials = {"username": "g1-action", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.views.discover_tab_cache.invalidate_for_feedback_change")
    @patch("app.views.discover_tab_cache.update_undo_snapshot")
    @patch("app.views.discover_tab_cache.apply_cached_action", return_value=None)
    @patch("app.views.discover_tab_cache.store_undo_snapshot", return_value="undo-g1")
    @patch("app.views.ensure_item_metadata")
    @patch("app.views.discover_tab_cache.get_tab_rows")
    def test_hide_answers_json_with_undo(self, mock_rows, mock_ensure, *_):
        item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
        )
        mock_ensure.return_value = HydratedItemResult(item=item, metadata={}, created=False)
        response = self.client.post(
            reverse("discover_action"),
            {
                "action": "dismiss",
                "candidate_media_type": "movie",
                "source": "tmdb",
                "media_id": "603",
                "active_media_type": "all",
                "show_more": "0",
                "row_key": "top_picks_for_you",
                "title": "The Matrix",
            },
            **JSON,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["action"], "dismiss")
        self.assertEqual(body["undo_token"], "undo-g1")
        self.assertIn("The Matrix", body["message"])
        self.assertNotIn("HX-Trigger", response)
        # The screen re-reads its rows: the action renders none.
        mock_rows.assert_not_called()
        self.assertTrue(
            DiscoverFeedback.objects.filter(user=self.user, item=item).exists(),
        )

    def test_bad_action_answers_json_400(self, *_):
        response = self.client.post(reverse("discover_action"), {"action": "nope"}, **JSON)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Invalid action"})

    @patch("app.views.discover_tab_cache.restore_undo_snapshot", return_value={"rows": []})
    @patch("app.views.discover_tab_cache.get_undo_snapshot", return_value={"side_effect": {}})
    def test_undo_answers_json(self, *_):
        response = self.client.post(
            reverse("discover_action"),
            {"action": "undo", "undo_token": "undo-g1", "active_media_type": "all"},
            **JSON,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["action"], "undo")
