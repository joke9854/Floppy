from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from users.models import ThemeChoices

# Every target the CineTrack rail, bottom nav and their menus link to.
NAV_TARGETS = [
    ("home", {}),
    ("discover", {}),
    ("medialist", {"media_type": "tv"}),
    ("calendar", {}),
    ("history", {}),
    ("statistics", {}),
    ("lists", {}),
    ("collection_list", {}),
    ("tag_index", {}),
    ("create_entry", {}),
    ("account", {}),
    ("appearance", {}),
]


class CineTrackShellTests(TestCase):
    """The W1 shell replaces the sidebar for the CineTrack theme only."""

    def setUp(self):
        self.credentials = {"username": "shell", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _use_theme(self, theme):
        self.user.theme = theme
        self.user.save(update_fields=["theme"])

    def test_cinetrack_renders_rail_and_bottom_nav_instead_of_sidebar(self):
        self._use_theme(ThemeChoices.CINETRACK)
        for name, kwargs in NAV_TARGETS:
            with self.subTest(name=name):
                response = self.client.get(reverse(name, kwargs=kwargs))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="ct-rail ct-glass hidden md:flex"')
                self.assertContains(response, 'class="ct-bottom-nav ct-glass md:hidden"')
                self.assertContains(response, "data-ct-shell")
                self.assertNotContains(response, "<aside")
                self.assertNotContains(response, "isMobileMenuOpen = !isMobileMenuOpen")

    def test_classic_theme_keeps_the_sidebar(self):
        self._use_theme(ThemeChoices.DARK)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "<aside")
        self.assertNotContains(response, "ct-rail")
        self.assertNotContains(response, "data-ct-shell")

    def test_view_transition_opt_in_skips_pages_that_never_opt_in(self):
        self._use_theme(ThemeChoices.CINETRACK)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "@view-transition { navigation: auto; }")
        self.assertContains(response, 'addEventListener("pageswap"')
        self.assertContains(response, 'pathname.startsWith("/accounts/")')

        self._use_theme(ThemeChoices.DARK)
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "@view-transition")
        self.assertNotContains(response, "pageswap")

    def test_current_page_is_marked_for_assistive_tech(self):
        self._use_theme(ThemeChoices.CINETRACK)
        response = self.client.get(reverse("calendar"))
        html = response.content.decode()
        calendar_url = reverse("calendar")
        self.assertRegex(
            html,
            rf'<a href="{calendar_url}"\s+class="ct-rail-link"\s+aria-current="page">',
        )
        self.assertRegex(
            html,
            rf'<a href="{calendar_url}"\s+class="ct-tab"\s+aria-current="page">',
        )

    def test_menu_toggles_expose_expanded_state_and_controls(self):
        self._use_theme(ThemeChoices.CINETRACK)
        response = self.client.get(reverse("home"))
        for menu_id in (
            "ct-rail-library-menu",
            "ct-rail-account-menu",
            "ct-sheet-library-menu",
            "ct-sheet-more-menu",
        ):
            with self.subTest(menu=menu_id):
                self.assertContains(response, f'aria-controls="{menu_id}"')
                self.assertContains(response, f'id="{menu_id}"')
        self.assertContains(response, 'aria-haspopup="true"', count=4)
