# FORK: tests for discover, home, and collection-parity API endpoints.
from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from app.models import CollectionEntry, DiscoverFeedback, MediaTypes

from .base import FloppyApiTestCase


class CollectionStatusTests(FloppyApiTestCase):
    """GET collection/status/{item_id}."""

    def test_status_reflects_collection(self):
        """Items with entries report has_collection_data true."""
        item = self.items_by_type[MediaTypes.MOVIE.value][0]
        no_entry = self.call_api(
            "get",
            "api_collection_status",
            args=(item.id,),
            headers=self.auth_headers,
        )
        self.assertEqual(no_entry.status_code, HTTP.OK)
        self.assertFalse(no_entry.json()["has_collection_data"])

        CollectionEntry.objects.create(user=self.user1, item=item)
        with_entry = self.call_api(
            "get",
            "api_collection_status",
            args=(item.id,),
            headers=self.auth_headers,
        )
        self.assertTrue(with_entry.json()["has_collection_data"])

    def test_unknown_item_not_found(self):
        """Unknown item ids 404."""
        response = self.call_api(
            "get",
            "api_collection_status",
            args=(999999,),
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)


class CollectionSeasonTests(FloppyApiTestCase):
    """DELETE collection/seasons/{season_item_id}."""

    def test_no_sonarr_entries_not_found(self):
        """Seasons without Sonarr-backed collected episodes return 404."""
        season_item = self.items_by_type[MediaTypes.SEASON.value][0]
        response = self.call_api(
            "delete",
            "api_collection_season",
            args=(season_item.id,),
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)


class DiscoverTests(FloppyApiTestCase):
    """Discover rows, refresh, and hidden toggles."""

    @patch("api.fork_views_discover._discover_response_rows", return_value=[])
    def test_rows_endpoint(self, _mock_rows):
        """GET discover returns the resolved media type and rows."""
        response = self.call_api(
            "get",
            "api_discover",
            params={"media_type": MediaTypes.MOVIE.value},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK)
        payload = response.json()
        self.assertEqual(payload["media_type"], MediaTypes.MOVIE.value)
        self.assertEqual(payload["rows"], [])

    @patch("api.fork_views_discover.discover_tab_cache.schedule_tab_refresh")
    def test_refresh_queues_rebuild(self, mock_schedule):
        """POST discover/refresh returns 202 and schedules a rebuild."""
        response = self.call_api(
            "post",
            "api_discover_refresh",
            payload={"media_type": MediaTypes.MOVIE.value},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        mock_schedule.assert_called_once()

    def test_hide_and_unhide_item(self):
        """POST discover/hidden toggles NOT_INTERESTED feedback."""
        item = self.items_by_type[MediaTypes.MOVIE.value][0]
        hidden = self.call_api(
            "post",
            "api_discover_hidden",
            payload={"item_id": item.id, "action": "hide"},
            headers=self.auth_headers,
        )
        self.assertEqual(hidden.status_code, HTTP.OK)
        self.assertTrue(
            DiscoverFeedback.objects.filter(user=self.user1, item=item).exists(),
        )

        listed = self.call_api(
            "get",
            "api_discover_hidden",
            headers=self.auth_headers,
        )
        self.assertEqual(len(listed.json()["results"]), 1)

        unhidden = self.call_api(
            "post",
            "api_discover_hidden",
            payload={"item_id": item.id, "action": "unhide"},
            headers=self.auth_headers,
        )
        self.assertEqual(unhidden.status_code, HTTP.OK)
        self.assertFalse(
            DiscoverFeedback.objects.filter(user=self.user1, item=item).exists(),
        )

    def test_invalid_action_rejected(self):
        """Unknown hidden actions return 400."""
        response = self.call_api(
            "post",
            "api_discover_hidden",
            payload={"item_id": 1, "action": "nope"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)


class HomeTests(FloppyApiTestCase):
    """GET /home returns serialized home groups."""

    def test_home_groups(self):
        """Groups are the Home sections in order, one row each, with cards."""
        response = self.call_api("get", "api_home", headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        groups = response.json()["groups"]
        self.assertTrue(groups)
        section_order = ["in_progress", "airing", "recent", "coming_soon"]
        keys = [group["media_type"] for group in groups]
        self.assertEqual(keys, [key for key in section_order if key in keys])
        first_row = groups[0]["rows"][0]
        self.assertEqual(first_row["row_id"], groups[0]["media_type"])
        self.assertTrue(first_row["items"])
        row_item = first_row["items"][0]
        # Regression guard for the HomeRowEntry serializer_map gap: items must
        # not fall back to a bare {"title": ...} dict.
        self.assertIn("id", row_item)
        self.assertIn("item", row_item)
        self.assertIn("url", row_item["item"])
        self.assertIn("ids", row_item["item"])
        self.assertIn("image", row_item["item"])

    def test_home_invalid_limit_rejected(self):
        """Non-numeric limits return 400."""
        response = self.call_api(
            "get",
            "api_home",
            params={"limit": "abc"},
            headers=self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
