"""Partial posts to the preferences endpoint must not reset fields they omit.

Any field the view reads with a fallback instead of a presence check would be
reset to that fallback on every partial post, so this pins the partial-post contract.
"""

from django.test import TestCase
from django.urls import reverse

from users.models import QuickSeasonUpdateChoices, User


class ThemeTogglePartialPostTests(TestCase):
    """A partial post must change only the fields it sends."""

    def setUp(self):
        """Sign in a user carrying non-default preference values."""
        self.user = User.objects.create_user(username="toggler", password="p12345678")
        self.user.quick_season_update_mobile = QuickSeasonUpdateChoices.values[-1]
        self.user.book_comic_manga_progress_percentage = True
        self.user.progress_bar = True
        self.user.hide_zero_rating = True
        self.user.save()
        self.client.force_login(self.user)

    def test_spoiler_protection_switches_save(self):
        """Both spoiler switches persist, and the page offers them."""
        self.client.post(
            reverse("preferences"),
            {"obfuscate_episodes": "1", "hide_episode_overviews": "0"},
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.obfuscate_episodes)
        self.assertFalse(self.user.hide_episode_overviews)
        page = self.client.get(reverse("preferences"))
        self.assertContains(page, 'name="obfuscate_episodes"')
        self.assertContains(page, 'name="hide_episode_overviews"')

    def test_partial_post_preserves_unrelated_preferences(self):
        """Absent fields keep their stored value instead of falling back."""
        expected = {
            "quick_season_update_mobile": self.user.quick_season_update_mobile,
            "book_comic_manga_progress_percentage": True,
            "progress_bar": True,
            "hide_zero_rating": True,
        }

        self.client.post(reverse("preferences"), {"obfuscate_episodes": "1"})

        self.user.refresh_from_db()
        self.assertTrue(self.user.obfuscate_episodes)
        for field, value in expected.items():
            self.assertEqual(
                getattr(self.user, field),
                value,
                f"a partial post reset {field}",
            )

    def test_preferences_form_can_still_clear_a_boolean(self):
        """A real form post that omits a checkbox must still turn it off."""
        self.client.post(
            reverse("preferences"),
            {"book_comic_manga_progress_percentage": "0"},
        )

        self.user.refresh_from_db()
        self.assertFalse(self.user.book_comic_manga_progress_percentage)
