"""Phase 6 of the v2 layout: Settings (A5/A22) for CineTrack and the A15 login."""

from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app import login_wall
from app.discover.schemas import CandidateItem
from integrations.models import PlexAccount


class CineTrackSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="ct-settings",
            password="testpass123",
            theme="cinetrack",
        )
        self.client.force_login(self.user)

    def test_settings_nav_is_grouped_and_hides_rss_and_about(self):
        response = self.client.get(reverse("account"))

        self.assertContains(response, 'class="ct-settings-nav"')
        self.assertContains(response, 'class="ct-settings-group"', count=3)
        self.assertContains(response, "Media types")
        self.assertContains(response, reverse("preferences"))
        self.assertNotContains(response, f'href="{reverse("rss_settings")}"')
        self.assertNotContains(response, f'href="{reverse("about")}"')

    def test_integrations_opens_on_card_grid(self):
        response = self.client.get(reverse("integrations"))

        self.assertContains(response, "activeIntegration: 'grid'")
        self.assertContains(response, 'class="ct-integrations-grid"')
        self.assertContains(response, "Media servers")
        self.assertContains(response, "Apps & services")
        self.assertContains(response, "?open=trakt")
        self.assertContains(response, "?open=pocketcasts")
        # The pill filter bar is replaced by the cards; tokens sit in the API view.
        self.assertNotContains(response, "Jump to integration")
        self.assertContains(response, "x-show=\"activeIntegration === 'api'\"")

    def test_plex_card_reports_stored_connection(self):
        PlexAccount.objects.create(user=self.user, plex_token="token")

        response = self.client.get(reverse("integrations"))

        self.assertContains(response, 'aria-label="Manage Plex"')
        self.assertContains(response, 'aria-label="Connect Jellyfin"')
        self.assertContains(response, 'aria-label="Set up Emby"')

    def test_appearance_uses_theme_tiles_and_hides_detail_layouts(self):
        response = self.client.get(reverse("appearance"))

        self.assertContains(response, "ct-appearance")
        self.assertContains(response, 'class="ct-theme-preview" data-theme="cinetrack"')
        self.assertContains(response, 'class="preferences-section" hidden')

    def test_connected_apps_links_to_integrations_api_view(self):
        response = self.client.get(reverse("connected_apps"))

        self.assertContains(response, f'{reverse("integrations")}?open=api#connected-apps')


class ClassicSettingsTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="classic-settings",
            password="testpass123",
            theme="dark",
        )
        self.client.force_login(self.user)

    def test_integrations_keep_filter_bar_and_classic_nav(self):
        response = self.client.get(reverse("integrations"))

        self.assertContains(response, "activeIntegration: 'all'")
        self.assertContains(response, "Jump to integration")
        self.assertNotContains(response, "ct-integrations-grid")
        self.assertNotContains(response, "ct-settings-nav")
        self.assertContains(response, f'href="{reverse("rss_settings")}"')

    def test_appearance_keeps_detail_layouts(self):
        response = self.client.get(reverse("appearance"))

        self.assertNotContains(response, "ct-theme-preview")
        self.assertNotContains(response, 'class="preferences-section" hidden')


class V2LoginTests(TestCase):
    def test_anonymous_login_uses_v2_layout(self):
        # An existing user, so the page is the sign-in and not the first-run welcome.
        get_user_model().objects.create_user(username="existing", password="testpass123")

        response = self.client.get(reverse("account_login"))

        self.assertContains(response, 'class="cinetrack bg-')
        self.assertContains(response, 'class="ct-login"')
        self.assertContains(response, "Sign in to Floppy")
        self.assertContains(response, 'name="login"')
        self.assertContains(response, 'name="password"')
        self.assertContains(response, reverse("password_recover"))
        self.assertContains(response, '<meta name="floppy-page" content="entrance">')

    def test_login_still_signs_in(self):
        get_user_model().objects.create_user(username="v2-login", password="testpass123")

        response = self.client.post(
            reverse("account_login"),
            {"login": "v2-login", "password": "testpass123"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("_auth_user_id", self.client.session)

    def test_failed_login_shows_error_on_v2_layout(self):
        response = self.client.post(
            reverse("account_login"),
            {"login": "nobody", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="ct-login"')
        self.assertContains(response, "not correct")


class LoginPosterWallTests(TestCase):
    def setUp(self):
        cache.delete(login_wall.CACHE_KEY)
        cache.delete(login_wall.LOCK_KEY)

    def test_cached_posters_render_with_tmdb_credit(self):
        poster = "https://image.tmdb.org/t/p/w342/poster.jpg"
        cache.set(login_wall.CACHE_KEY, [poster], 60)

        with mock.patch("app.tasks.refresh_login_wall_posters.delay") as delay:
            response = self.client.get(reverse("account_login"))

        delay.assert_not_called()
        self.assertContains(response, f"background-image: url('{poster}')", count=2)
        self.assertContains(response, "artwork from TMDB")

    def test_cache_miss_schedules_one_refresh_and_keeps_placeholders(self):
        with mock.patch("app.tasks.refresh_login_wall_posters.delay") as delay:
            first = self.client.get(reverse("account_login"))
            self.client.get(reverse("account_login"))

        delay.assert_called_once_with()
        self.assertNotContains(first, "background-image")
        self.assertNotContains(first, "artwork from TMDB")

    def test_refresh_keeps_public_trending_posters_only(self):
        def trending(media_type, *, limit):
            return [
                CandidateItem(
                    media_type=media_type,
                    source="tmdb",
                    media_id=f"{media_type}-1",
                    title="Trending",
                    image=f"https://image.tmdb.org/t/p/w500/{media_type}.jpg",
                ),
                CandidateItem(
                    media_type=media_type,
                    source="tmdb",
                    media_id=f"{media_type}-2",
                    title="No poster",
                    image=login_wall.settings.IMG_NONE,
                ),
            ]

        with mock.patch(
            "app.discover.providers.tmdb_adapter.TMDbDiscoverAdapter.trending",
            side_effect=trending,
        ):
            posters = login_wall.refresh_posters()

        self.assertEqual(
            posters,
            [
                "https://image.tmdb.org/t/p/w342/movie.jpg",
                "https://image.tmdb.org/t/p/w342/tv.jpg",
            ],
        )
        self.assertEqual(cache.get(login_wall.CACHE_KEY), posters)
