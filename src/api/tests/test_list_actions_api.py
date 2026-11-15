"""FORK (P1-E): share a view, bulk-add to a list, list CSV export and import."""

import csv
from http import HTTPStatus as HTTP  # noqa: N814
from io import BytesIO, StringIO
from unittest.mock import patch

from integrations.upload_staging import discard_staged_upload
from lists.models import CustomList, CustomListItem, ListActivity

from .base import FloppyApiTestCase

SYNC_TASK = "lists.tasks.sync_smart_list_task.delay"
IMPORT_TASK = "lists.tasks.import_list_csv_task.delay"


class ListShareViewTests(FloppyApiTestCase):
    def _share(self, payload):
        return self.call_api(
            "post", "api_list_share_view", payload=payload, headers=self.auth_headers
        )

    @patch(SYNC_TASK)
    def test_share_creates_then_reuses_the_public_smart_list(self, sync):
        created = self._share({"media_type": "movie", "status": ["Completed"]})

        self.assertEqual(created.status_code, HTTP.CREATED)
        body = created.json()
        self.assertTrue(body["created"])
        custom_list = CustomList.objects.get(id=body["list_id"])
        self.assertEqual(custom_list.owner, self.user1)
        self.assertEqual(custom_list.visibility, "public")
        self.assertTrue(custom_list.is_smart)
        self.assertEqual(custom_list.smart_media_types, ["movie"])
        self.assertEqual(body["url"], custom_list.get_absolute_url())
        sync.assert_called_once_with(custom_list.id)

        again = self._share({"media_type": "movie", "status": ["Completed"]})

        self.assertEqual(again.status_code, HTTP.OK)
        self.assertEqual(again.json()["list_id"], custom_list.id)
        self.assertFalse(again.json()["created"])

    @patch(SYNC_TASK)
    def test_invalid_media_type_is_400(self, _sync):
        self.assertEqual(
            self._share({"media_type": "nope"}).status_code, HTTP.BAD_REQUEST
        )
        self.assertEqual(self._share({}).status_code, HTTP.BAD_REQUEST)


class ListBulkAddTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.custom_list = CustomList.objects.create(name="Mine", owner=self.user1)
        self.items = [media.item for media in self.movie_medias[:2]]

    def _add(self, item_ids, list_id=None, headers=None):
        return self.call_api(
            "post",
            "api_list_items_bulk",
            args=(list_id or self.custom_list.id,),
            payload={"item_ids": item_ids},
            headers=headers or self.auth_headers,
        )

    def test_adds_new_items_and_counts_the_rest(self):
        CustomListItem.objects.create(custom_list=self.custom_list, item=self.items[0])

        response = self._add([self.items[0].id, self.items[1].id, 987654])

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(), {"added": 1, "already_present": 1, "skipped": 1}
        )
        self.assertEqual(
            set(self.custom_list.items.values_list("id", flat=True)),
            {self.items[0].id, self.items[1].id},
        )
        self.assertTrue(
            ListActivity.objects.filter(
                custom_list=self.custom_list, item=self.items[1]
            ).exists()
        )

    def test_smart_list_is_403(self):
        self.custom_list.is_smart = True
        self.custom_list.save(update_fields=["is_smart"])
        self.assertEqual(self._add([self.items[0].id]).status_code, HTTP.FORBIDDEN)

    def test_other_users_list_and_bad_ids(self):
        other = CustomList.objects.create(name="Theirs", owner=self.user2)
        self.assertEqual(
            self._add([self.items[0].id], list_id=other.id).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(self._add([]).status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self._add(["x"]).status_code, HTTP.BAD_REQUEST)


class ListExportImportTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.custom_list = CustomList.objects.create(name="My Movies", owner=self.user1)
        CustomListItem.objects.create(
            custom_list=self.custom_list, item=self.movie_medias[0].item
        )

    def test_export_streams_the_list_csv(self):
        response = self.call_api(
            "get",
            "api_list_export",
            args=(self.custom_list.id,),
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn('filename="my-movies.csv"', response["Content-Disposition"])
        content = b"".join(response.streaming_content).decode("utf-8")
        rows = list(csv.DictReader(StringIO(content)))
        self.assertIn("list_item", {row["row_type"] for row in rows})

    def test_private_list_of_another_user_is_404(self):
        response = self.call_api(
            "get",
            "api_list_export",
            args=(self.custom_list.id,),
            headers=self.auth_headers2,
        )
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)

    @patch(IMPORT_TASK)
    def test_import_queues_the_staged_upload(self, delay):
        delay.return_value.id = "task-1"
        upload = BytesIO(b'"row_type","list_name"\n"list","Imported"\n')
        upload.name = "list.csv"

        response = self.call_api(
            "post",
            "api_list_import",
            payload={"file": upload},
            headers=self.auth_headers,
            content_type=None,
        )

        self.assertEqual(response.status_code, HTTP.ACCEPTED)
        self.assertEqual(response.json(), {"task_id": "task-1"})
        user_id, staged, mode = delay.call_args.args
        self.addCleanup(discard_staged_upload, staged)
        self.assertEqual((user_id, mode), (self.user1.id, "new"))
        self.assertTrue(staged.endswith(".csv"))

    def test_import_without_file_is_400(self):
        response = self.call_api(
            "post",
            "api_list_import",
            payload={},
            headers=self.auth_headers,
            content_type=None,
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
