"""FORK (P1-E): Trakt and MDBList list imports through the API."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

import requests
from django.core.cache import cache

from app.providers import services
from integrations.imports import helpers as import_helpers
from integrations.models import MDBListAccount, TraktAccount

from .base import FloppyApiTestCase

DEVICE_CODE = "integrations.imports.trakt.request_device_code"
POLL = "integrations.imports.trakt.poll_device_token"
TRAKT_TASK = "lists.tasks.import_trakt_lists_task.delay"
MDBLIST_TASK = "lists.tasks.import_mdblist_lists_task.delay"
MDBLIST_LIST_TASK = "lists.tasks.import_mdblist_list_by_reference_task.delay"
VALIDATE = "lists.imports.mdblist.validate_api_key"

DEVICE = {
    "device_code": "secret-device-code",
    "user_code": "ABCD1234",
    "verification_url": "https://trakt.tv/activate",
    "interval": 5,
    "expires_in": 600,
}


def _unreachable(message):
    """MediaImportError raised from a network failure, as the Trakt helpers do."""
    error = import_helpers.MediaImportError(message)
    error.__cause__ = services.ProviderAPIError(
        "trakt", requests.exceptions.ReadTimeout("x")
    )
    return error


class TraktListImportTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()

    def _call(self, method, name, payload=None):
        return self.call_api(method, name, payload=payload, headers=self.auth_headers)

    def _save_credentials(self):
        return self._call(
            "put",
            "api_list_imports_trakt_credentials",
            {"client_id": "cid", "client_secret": "csecret"},
        )

    def test_credentials_are_stored_encrypted_and_never_returned(self):
        self.assertEqual(self._save_credentials().status_code, HTTP.NO_CONTENT)

        account = TraktAccount.objects.get(user=self.user1)
        self.assertNotEqual(account.client_secret, "csecret")
        self.assertEqual(import_helpers.decrypt(account.client_secret), "csecret")
        status = self._call("get", "api_list_imports_status")
        self.assertEqual(status.status_code, HTTP.OK)
        self.assertTrue(status.json()["trakt"]["has_credentials"])
        self.assertNotIn("csecret", status.content.decode())

    def test_missing_credentials_are_400(self):
        self.assertEqual(
            self._call(
                "put", "api_list_imports_trakt_credentials", {"client_id": "cid"}
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self._call("post", "api_list_imports_trakt_device").status_code,
            HTTP.BAD_REQUEST,
        )

    @patch(TRAKT_TASK)
    @patch(POLL)
    @patch(DEVICE_CODE, return_value=DEVICE)
    def test_device_flow_pending_then_importing(self, device_code, poll, task):
        self._save_credentials()

        started = self._call("post", "api_list_imports_trakt_device")

        self.assertEqual(started.status_code, HTTP.OK)
        self.assertEqual(
            started.json(),
            {
                "user_code": "ABCD1234",
                "verification_url": "https://trakt.tv/activate",
                "interval": 5,
                "expires_in": 600,
            },
        )
        self.assertNotIn("secret-device-code", started.content.decode())
        device_code.assert_called_once_with(client_id="cid")

        poll.return_value = None
        pending = self._call("post", "api_list_imports_trakt_poll")
        self.assertEqual(pending.json(), {"status": "pending", "interval": 5})

        poll.return_value = {"access_token": "token", "refresh_token": "r"}
        task.return_value.id = "task-9"
        done = self._call("post", "api_list_imports_trakt_poll")

        self.assertEqual(done.json(), {"status": "importing", "task_id": "task-9"})
        poll.assert_called_with(
            "secret-device-code", client_id="cid", client_secret="csecret"
        )
        task.assert_called_once_with(self.user1.id, "token", client_id="cid")
        # The code is spent.
        self.assertEqual(
            self._call("post", "api_list_imports_trakt_poll").status_code, HTTP.GONE
        )

    @patch(POLL)
    @patch(DEVICE_CODE, return_value=DEVICE)
    def test_denied_is_400_and_unreachable_is_503_keeping_the_code(
        self, _device_code, poll
    ):
        self._save_credentials()
        self._call("post", "api_list_imports_trakt_device")

        poll.side_effect = _unreachable("Could not reach Trakt. Try again.")
        unreachable = self._call("post", "api_list_imports_trakt_poll")
        self.assertEqual(unreachable.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(unreachable.json()["code"], "provider_unavailable")

        poll.side_effect = import_helpers.MediaImportError(
            "Trakt authorization was denied."
        )
        denied = self._call("post", "api_list_imports_trakt_poll")
        self.assertEqual(denied.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(denied.json()["detail"], "Trakt authorization was denied.")
        self.assertEqual(
            self._call("post", "api_list_imports_trakt_poll").status_code, HTTP.GONE
        )

    @patch(DEVICE_CODE, side_effect=_unreachable("Could not start Trakt authorization."))
    def test_trakt_down_when_starting_is_503(self, _device_code):
        self._save_credentials()
        response = self._call("post", "api_list_imports_trakt_device")
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)

    def test_poll_without_a_pending_code_is_410(self):
        response = self._call("post", "api_list_imports_trakt_poll")
        self.assertEqual(response.status_code, HTTP.GONE)
        self.assertEqual(response.json()["code"], "expired")


class MDBListImportTests(FloppyApiTestCase):
    def _call(self, method, name, payload=None):
        return self.call_api(method, name, payload=payload, headers=self.auth_headers)

    @patch(MDBLIST_TASK)
    @patch(VALIDATE, return_value={"username": "u"})
    def test_connect_sync_import_and_disconnect(self, validate, task):
        task.return_value.id = "task-1"

        connected = self._call(
            "put", "api_list_imports_mdblist", {"api_key": "key", "sync_frequency": "12h"}
        )

        self.assertEqual(connected.status_code, HTTP.ACCEPTED)
        self.assertEqual(connected.json(), {"task_id": "task-1"})
        validate.assert_called_once_with("key")
        account = MDBListAccount.objects.get(user=self.user1)
        self.assertEqual(account.sync_frequency, "12h")
        self.assertEqual(import_helpers.decrypt(account.api_key), "key")
        status = self._call("get", "api_list_imports_status").json()["mdblist"]
        self.assertTrue(status["connected"])
        self.assertEqual(status["sync_frequency"], "12h")

        account.connection_broken = True
        account.save(update_fields=["connection_broken"])
        synced = self._call("post", "api_list_imports_mdblist_sync")
        self.assertEqual(synced.status_code, HTTP.ACCEPTED)
        account.refresh_from_db()
        self.assertFalse(account.connection_broken)

        with patch(MDBLIST_LIST_TASK) as list_task:
            list_task.return_value.id = "task-2"
            imported = self._call(
                "post",
                "api_list_imports_mdblist_import",
                {"list_reference": "https://mdblist.com/lists/u/top"},
            )
        self.assertEqual(imported.status_code, HTTP.ACCEPTED)
        list_task.assert_called_once_with(
            self.user1.id, "https://mdblist.com/lists/u/top"
        )

        self.assertEqual(
            self._call("delete", "api_list_imports_mdblist").status_code,
            HTTP.NO_CONTENT,
        )
        self.assertFalse(MDBListAccount.objects.filter(user=self.user1).exists())

    @patch(VALIDATE, side_effect=import_helpers.MediaImportError("bad"))
    def test_invalid_key_is_400(self, _validate):
        response = self._call("put", "api_list_imports_mdblist", {"api_key": "bad"})
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertFalse(MDBListAccount.objects.filter(user=self.user1).exists())

    @patch(VALIDATE, side_effect=requests.exceptions.ConnectionError("down"))
    def test_mdblist_down_is_503(self, _validate):
        response = self._call("put", "api_list_imports_mdblist", {"api_key": "key"})
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)

    def test_bad_input_and_not_connected(self):
        self.assertEqual(
            self._call("put", "api_list_imports_mdblist", {}).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self._call(
                "put",
                "api_list_imports_mdblist",
                {"api_key": "k", "sync_frequency": "hourly"},
            ).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self._call("post", "api_list_imports_mdblist_sync").status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self._call(
                "post", "api_list_imports_mdblist_import", {"list_reference": "x"}
            ).status_code,
            HTTP.NOT_FOUND,
        )
