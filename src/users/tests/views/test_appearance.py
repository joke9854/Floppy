import json
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from users.appearance import DETAIL_LAYOUT_FAMILIES
from users.templatetags.user_tags import detail_section_attrs


class AppearanceViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="appearance-user",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_appearance_exposes_distinct_detail_families(self):
        response = self.client.get(reverse("appearance"))

        self.assertContains(response, "Episodes")
        self.assertContains(response, "Music albums")
        self.assertNotEqual(
            DETAIL_LAYOUT_FAMILIES["episode"]["zones"],
            DETAIL_LAYOUT_FAMILIES["music_album"]["zones"],
        )

    def test_appearance_serializes_editor_data_once(self):
        response = self.client.get(reverse("appearance"))

        self.assertIsInstance(response.context["detail_layout_families_json"], dict)
        self.assertIsInstance(response.context["detail_layouts_json"], dict)
        self.assertNotContains(response, "overflow-x-auto")

    def test_appearance_persists_ordered_sections(self):
        layouts = {
            "media": {
                "sidebar": ["details", "genres"],
                "content": ["cast", "notes"],
            }
        }

        response = self.client.post(
            reverse("appearance"),
            {"detail_layouts": json.dumps(layouts)},
        )

        self.assertRedirects(response, reverse("appearance"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.detail_page_layouts["media"], layouts["media"])

    def test_appearance_rejects_unknown_sections_without_partial_save(self):
        response = self.client.post(
            reverse("appearance"),
            {
                "detail_layouts": json.dumps(
                    {"episode": {"content": ["notes", "not-a-section"]}}
                ),
            },
        )

        self.assertRedirects(response, reverse("appearance"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.detail_page_layouts, {})

    def test_appearance_saves_the_floating_sidebar(self):
        response = self.client.post(
            reverse("appearance"),
            {
                "detail_layouts": "{}",
                "sidebar_style": "floating",
                "floating_sidebar": "icons",
            },
        )

        self.assertRedirects(response, reverse("appearance"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.sidebar_style, "floating")
        self.assertEqual(self.user.floating_sidebar, "icons")

    def test_appearance_keeps_the_sidebar_when_the_form_omits_it(self):
        self.user.sidebar_style = "floating"
        self.user.save(update_fields=["sidebar_style"])

        self.client.post(
            reverse("appearance"),
            {"detail_layouts": "{}"},
        )

        self.user.refresh_from_db()
        self.assertEqual(self.user.sidebar_style, "floating")

    def test_appearance_rejects_an_unknown_sidebar_without_partial_save(self):
        response = self.client.post(
            reverse("appearance"),
            {
                "detail_layouts": "{}",
                "sidebar_style": "docked",
            },
        )

        self.assertRedirects(response, reverse("appearance"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.sidebar_style, "attached")

    def test_detail_section_attributes_apply_visibility_and_order(self):
        self.user.detail_page_layouts = {
            "episode": {"content": ["crew", "notes"]}
        }

        self.assertIn(
            'data-detail-section="crew" style="order: 0"',
            str(detail_section_attrs(self.user, "episode", "content", "crew")),
        )
        self.assertIn(
            'data-detail-section="notes" style="order: 1"',
            str(detail_section_attrs(self.user, "episode", "content", "notes")),
        )
        self.assertIn(
            'data-detail-section="cast" hidden',
            str(detail_section_attrs(self.user, "episode", "content", "cast")),
        )

    def test_comic_publishers_are_visible_by_default(self):
        attributes = str(
            detail_section_attrs(self.user, "comic", "sidebar", "studios")
        )

        self.assertIn('data-detail-section="studios" style="order:', attributes)
        self.assertNotIn("hidden", attributes)
