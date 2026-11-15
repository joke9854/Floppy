"""FORK (P1-F): screen preferences through user/preferences and table columns."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from users.appearance import DETAIL_LAYOUT_FAMILIES

from .base import FloppyApiTestCase


class ScreenPreferencesTests(FloppyApiTestCase):
    def _patch(self, payload):
        return self.call_api(
            "patch", "api_user_preferences", payload=payload, headers=self.auth_headers
        )

    def test_new_fields_are_read_with_their_choices(self):
        response = self.call_api(
            "get", "api_user_preferences", headers=self.auth_headers
        ).json()
        for field in (
            "statistics_compare_mode",
            "genre_sort_by",
            "studio_sort_by",
            "sidebar_style",
            "floating_sidebar",
            "stats_split_tv_anime",
            "movie_show_each_play",
            "book_show_each_play",
            "pinned_watch_providers",
            "detail_page_layouts",
        ):
            self.assertIn(field, response["preferences"])
        self.assertIn("genre_sort_by", response["choices"])
        self.assertIn("sidebar_style", response["choices"])

    @patch("api.fork_views_users.cache_utils.clear_media_list_cache_for_user")
    def test_entry_grouping_clears_the_list_cache(self, clear):
        response = self._patch({"movie_show_each_play": True})

        self.assertEqual(response.status_code, HTTP.OK)
        self.user1.refresh_from_db()
        self.assertTrue(self.user1.movie_show_each_play)
        clear.assert_called_once_with(self.user1.id)

    @patch("api.fork_views_users.statistics_cache.schedule_all_ranges_refresh")
    @patch("api.fork_views_users.statistics_cache.invalidate_all_statistics_days")
    def test_splitting_tv_and_anime_rebuilds_statistics(self, invalidate_days, _refresh):
        value = not self.user1.stats_split_tv_anime
        response = self._patch({"stats_split_tv_anime": value})

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["updated_fields"], ["stats_split_tv_anime"])
        invalidate_days.assert_called_once()

    def test_statistics_sorts_are_validated(self):
        self.assertEqual(
            self._patch({"genre_sort_by": "nonsense"}).status_code, HTTP.BAD_REQUEST
        )
        choices = self.call_api(
            "get", "api_user_preferences", headers=self.auth_headers
        ).json()["choices"]["studio_sort_by"]
        target = next(value for value in choices if value != self.user1.studio_sort_by)
        self.assertEqual(self._patch({"studio_sort_by": target}).status_code, HTTP.OK)
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.studio_sort_by, target)

    def test_pinned_providers_replace_the_list(self):
        response = self._patch(
            {"pinned_watch_providers": [" Netflix ", "Mubi", "Netflix"]}
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json()["preferences"]["pinned_watch_providers"],
            ["Netflix", "Mubi"],
        )
        for bad in ("Netflix", [""], [3], ["x"] * 101):
            with self.subTest(bad=bad):
                self.assertEqual(
                    self._patch({"pinned_watch_providers": bad}).status_code,
                    HTTP.BAD_REQUEST,
                )

    def test_detail_page_layouts_are_validated(self):
        family_key, family = next(iter(DETAIL_LAYOUT_FAMILIES.items()))
        zone_key, zone = next(iter(family["zones"].items()))
        section = zone["sections"][0]["key"]
        layouts = {family_key: {zone_key: [section]}}

        response = self._patch({"detail_page_layouts": layouts})

        self.assertEqual(response.status_code, HTTP.OK)
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.detail_page_layouts, layouts)
        for bad in ({"nope": {}}, {family_key: {zone_key: ["nope"]}}, ["list"]):
            with self.subTest(bad=bad):
                self.assertEqual(
                    self._patch({"detail_page_layouts": bad}).status_code,
                    HTTP.BAD_REQUEST,
                )


class TableColumnsTests(FloppyApiTestCase):
    def _get(self, params):
        return self.call_api(
            "get", "api_user_table_columns", params=params, headers=self.auth_headers
        )

    def _put(self, payload):
        return self.call_api(
            "put", "api_user_table_columns", payload=payload, headers=self.auth_headers
        )

    def test_hide_and_reorder_movie_columns(self):
        columns = self._get({"media_type": "movie"}).json()["columns"]
        keys = [column["key"] for column in columns]
        self.assertTrue(all(column["visible"] for column in columns))

        response = self._put(
            {
                "media_type": "movie",
                "order": [keys[-1], "not-a-column"],
                "hidden": [keys[0], "not-a-column"],
            }
        )

        self.assertEqual(response.status_code, HTTP.OK)
        saved = response.json()["columns"]
        self.assertEqual(saved[0]["key"], keys[-1])
        visibility = {column["key"]: column["visible"] for column in saved}
        self.assertFalse(visibility[keys[0]])
        self.assertEqual(
            self._get({"media_type": "movie"}).json()["columns"], saved
        )

    def test_list_tables_are_separate_from_library_tables(self):
        list_columns = self._get({"table_type": "list", "media_type": "all"})
        self.assertEqual(list_columns.status_code, HTTP.OK)
        self.assertEqual(list_columns.json()["sort"], "date_added")
        key = list_columns.json()["columns"][0]["key"]

        self._put({"table_type": "list", "media_type": "all", "order": [], "hidden": [key]})

        relisted = self._get({"table_type": "list", "media_type": "all"}).json()
        self.assertFalse(
            next(c for c in relisted["columns"] if c["key"] == key)["visible"]
        )

    def test_sort_without_its_column_falls_back_to_title(self):
        response = self._get({"media_type": "book", "sort": "time_left"})
        self.assertEqual(response.json()["sort"], "title")

    def test_bad_targets_are_400(self):
        for params in (
            {},
            {"media_type": "nope"},
            {"media_type": "movie", "table_type": "album"},
            {"media_type": "movie", "sort": "nope"},
            {"media_type": "all"},
            {"media_type": "movie", "table_type": "list", "sort": "score"},
        ):
            with self.subTest(params=params):
                self.assertEqual(self._get(params).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(
            self._put({"media_type": "movie", "order": "x", "hidden": []}).status_code,
            HTTP.BAD_REQUEST,
        )


class AnimeLibraryConvertTests(FloppyApiTestCase):
    @patch("app.tasks_anime_library_repair.convert_anime_library_shape_task.delay")
    def test_queues_the_conversion(self, delay):
        delay.return_value.id = "task-7"
        response = self.call_api(
            "post", "api_user_anime_library_convert", headers=self.auth_headers
        )
        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        self.assertEqual(response.json(), {"task_id": "task-7"})
        delay.assert_called_once_with(self.user1.id)
