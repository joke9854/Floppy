"""Settings pages for the web (v2 P4-J1).

GET /api/v1/settings/screen/<page>/ reads each page as the Django view does;
the web saves through the Django forms with Accept: application/json. Each
form round-trips: the screen's values posted back change nothing.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

import events.tasks
from app.models import Item, MediaTypes, Sources
from users import appearance as appearance_config
from users.views import SIDEBAR_MEDIA_TYPES

JSON = {"HTTP_ACCEPT": "application/json"}


class SettingsScreenTests(TestCase):
    """The settings screen and the forms it posts to."""

    def setUp(self):
        self.credentials = {"username": "j1", "password": "j1-old-password-1"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _screen(self, page):
        response = self.client.get(reverse("api_settings_screen", args=[page]))
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def _row(self, *fields):
        self.user.refresh_from_db()
        return {field: getattr(self.user, field) for field in fields}

    def test_nav_marks_the_web_pages(self):
        screen = self._screen("account")
        self.assertTrue(screen["handled"])
        items = {item["slug"]: item for section in screen["nav"] for item in section["items"]}
        self.assertTrue(items["notifications"]["web"])
        self.assertTrue(items["preferences"]["web"])
        self.assertFalse(items["integrations"]["web"])
        self.assertEqual(items["metadata"]["href"], reverse("metadata_settings"))
        integrations = self._screen("integrations")
        self.assertFalse(integrations["handled"])
        self.assertEqual(integrations["django_url"], reverse("integrations"))
        self.assertFalse(self._screen("nope")["handled"])

    def test_account_username_and_password(self):
        account = self._screen("account")["account"]
        self.assertEqual(account["username"], "j1")
        same = self.client.post(account["save_url"], {"username": "j1"}, **JSON)
        self.assertEqual(same.json(), {"saved": True, "username": "j1"})

        wrong = self.client.post(
            account["save_url"],
            {"old_password": "not-it", "new_password1": "j1-new-Password-2", "new_password2": "j1-new-Password-2"},
            **JSON,
        )
        self.assertEqual(wrong.status_code, 400)
        self.assertIn("old_password", wrong.json()["errors"])

        changed = self.client.post(
            account["save_url"],
            {
                "old_password": self.credentials["password"],
                "new_password1": "j1-new-Password-2",
                "new_password2": "j1-new-Password-2",
            },
            **JSON,
        )
        self.assertEqual(changed.json(), {"saved": True})
        # The session survives the change (update_session_auth_hash).
        self.assertEqual(self.client.get(reverse("api_settings_screen", args=["account"])).status_code, 200)
        self.assertTrue(self.client.login(username="j1", password="j1-new-Password-2"))

    def test_notifications_round_trip_and_premiere(self):
        self.user.premiere_notifications_enabled = True
        self.user.notification_urls = "json://localhost"
        self.user.save()
        fields = (
            "notification_urls",
            "daily_digest_enabled",
            "release_notifications_enabled",
            "premiere_notifications_enabled",
        )
        before = self._row(*fields)
        notifications = self._screen("notifications")["notifications"]
        data = {"notification_urls": notifications["notification_urls"]}
        data.update({field: "on" for field in fields[1:] if notifications[field]})
        response = self.client.post(notifications["urls"]["save"], data, **JSON)
        self.assertEqual(response.json(), {"saved": True})
        self.assertEqual(self._row(*fields), before)

        # The API PATCH no longer turns the premiere digest off.
        patched = self.client.patch(
            reverse("api_user_notifications"),
            data=json.dumps({"daily_digest_enabled": True}),
            content_type="application/json",
        )
        self.assertEqual(patched.status_code, 200)
        self.assertTrue(self._row("premiere_notifications_enabled")["premiere_notifications_enabled"])

    def test_notification_exclusion_search(self):
        item = Item.objects.create(
            media_id="j1-1", source=Sources.MANUAL.value, media_type=MediaTypes.MOVIE.value, title="Quiet Harbour"
        )
        urls = self._screen("notifications")["notifications"]["urls"]
        found = self.client.get(urls["search"], {"q": "harbour"}, **JSON).json()["items"]
        self.assertEqual([row["id"] for row in found], [item.id])
        self.client.post(urls["exclusions"], data=json.dumps({"item_id": item.id}), content_type="application/json")
        self.assertEqual([row["id"] for row in self._screen("notifications")["notifications"]["excluded"]], [item.id])
        self.assertEqual(self.client.get(urls["search"], {"q": "harbour"}, **JSON).json()["items"], [])

    def test_media_types_round_trip(self):
        self.user.sidebar_media_type_order = list(reversed(SIDEBAR_MEDIA_TYPES))
        self.user.clickable_media_cards = True
        self.user.save()
        fields = ("clickable_media_cards", "sidebar_media_type_order", *(f"{value}_enabled" for value in SIDEBAR_MEDIA_TYPES))
        before = self._row(*fields)
        sidebar = self._screen("sidebar")["sidebar"]
        self.assertEqual([row["value"] for row in sidebar["media_types"]], list(reversed(SIDEBAR_MEDIA_TYPES)))
        data = {
            "media_types_checkboxes": [row["value"] for row in sidebar["media_types"] if row["enabled"]],
            "sidebar_media_type_order": ",".join(row["value"] for row in sidebar["media_types"]),
        }
        if sidebar["clickable_media_cards"]:
            data["clickable_media_cards"] = "on"
        response = self.client.post(sidebar["save_url"], data, **JSON)
        self.assertEqual(response.json(), {"saved": True, "changed": False})
        self.assertEqual(self._row(*fields), before)

    def test_appearance_round_trip(self):
        before = (
            appearance_config.resolved_detail_layouts(self.user.detail_page_layouts),
            self.user.sidebar_style,
            self.user.floating_sidebar,
        )
        appearance = self._screen("appearance")["appearance"]
        response = self.client.post(
            appearance["save_url"],
            {
                "sidebar_style": appearance["sidebar_style"],
                "floating_sidebar": appearance["floating_sidebar"],
                "detail_layouts": json.dumps(appearance["detail_layouts"]),
            },
            **JSON,
        )
        self.assertEqual(response.json(), {"saved": True})
        self.user.refresh_from_db()
        after = (
            appearance_config.resolved_detail_layouts(self.user.detail_page_layouts),
            self.user.sidebar_style,
            self.user.floating_sidebar,
        )
        self.assertEqual(after, before)
        bad = self.client.post(appearance["save_url"], {"sidebar_style": "sideways"}, **JSON)
        self.assertEqual(bad.status_code, 400)

    def test_about(self):
        about = self._screen("about")["about"]
        self.assertTrue(about["version"])
        self.assertEqual(about["urls"]["openapi"], reverse("openapi-contract"))

    def test_django_pages_still_answer_html(self):
        response = self.client.post(reverse("notifications"), {"notification_urls": ""})
        self.assertEqual(response.status_code, 302)
