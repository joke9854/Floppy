from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.tests.test_oauth_app_signin import VERIFIER, s256
from app.models import Item, MediaTypes, Movie, Sources, Status
from app.tests.views.test_history import _start_model_metadata_patches
from users.models import ThemeChoices
from users.templatetags.user_tags import user_time_format


class _ThemeMixin:
    credentials = {"username": "ct-pages", "password": "12345"}

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def _use_cinetrack(self):
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])


class CineTrackHistoryTests(_ThemeMixin, TestCase):
    """W5: History renders day groups of plays; a rewatch is its own row."""

    def setUp(self):
        super().setUp()
        _start_model_metadata_patches(self)
        self.first_play = timezone.now().replace(second=0, microsecond=0)
        self.second_play = self.first_play - timedelta(minutes=1)
        item = Item.objects.create(
            media_id="ct-rewatch",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatched Movie",
            image="http://example.com/poster.jpg",
        )
        for end_date in (self.first_play, self.second_play):
            Movie.objects.create(
                item=item,
                user=self.user,
                status=Status.COMPLETED.value,
                progress=1,
                end_date=end_date,
            )

    def test_cinetrack_rows_show_each_play_at_its_local_time(self):
        self._use_cinetrack()

        response = self.client.get(reverse("history"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/ct/history_day.html")
        self.assertContains(response, 'class="ct-history-row"', count=2)
        for play in (self.first_play, self.second_play):
            self.assertContains(response, user_time_format(play, self.user))
        self.assertContains(response, 'class="ct-history-head"')
        self.assertContains(response, "ct-fab ")
        self.assertContains(response, "htmx.swap(page, next.innerHTML")
        self.assertContains(response, 'data-ct-page="history"')

    def test_cinetrack_month_switcher_stops_at_the_current_month(self):
        import calendar

        next_month = calendar.month_abbr[timezone.localdate().month % 12 + 1]
        response = self.client.get(reverse("history"))

        self.assertNotContains(response, f"<span>{next_month}</span>")
        self.assertNotContains(response, "cursor-not-allowed text-sm")


class CineTrackPageShellTests(_ThemeMixin, TestCase):
    """W5: Calendar, Stats, Lists and Settings render their CineTrack pages."""

    def test_calendar_adds_the_phone_agenda(self):
        self._use_cinetrack()

        response = self.client.get(reverse("calendar"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ct-calendar")
        self.assertContains(response, 'class="ct-cal-mode md:hidden"')
        self.assertContains(response, 'class="ct-agenda"')

    def test_pages_carry_the_ct_marker(self):
        self._use_cinetrack()

        for name, marker in (
            ("statistics", 'data-ct-page="statistics"'),
            ("lists", 'data-ct-page="lists"'),
            ("account", "ct-settings"),
            ("preferences", "ct-settings"),
        ):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, marker)

    def test_settings_nav_cross_fades(self):
        response = self.client.get(reverse("account"))

        self.assertContains(response, 'hx-swap="innerHTML transition:true"', count=3)


class CineTrackSignInPagesTests(_ThemeMixin, TestCase):
    """W5: the app sign-in pages restyle for a ct user; fields and URLs stay."""

    def _authorize(self):
        return self.client.get(
            "/o/authorize/",
            {
                "client_id": "cinetrack",
                "response_type": "code",
                "redirect_uri": "cinetrack://floppy",
                "scope": "openid watchlist:read",
                "state": "state-123",
                "code_challenge": s256(VERIFIER),
                "code_challenge_method": "S256",
            },
        )

    def test_authorize_page_renders_with_the_same_form(self):
        response = self._authorize()

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "oauth2_provider/authorize.html")
        self.assertContains(response, "ct-entrance")
        self.assertContains(response, 'id="authorizationForm"')
        self.assertContains(response, 'name="allow"')

    def test_device_page_renders(self):
        self._use_cinetrack()

        response = self.client.get("/o/device/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ct-entrance")
        self.assertContains(response, 'id="id_user_code"')

    def test_signed_out_login_page_is_unchanged(self):
        self.client.logout()

        response = self.client.get(reverse("account_login"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "ct-entrance")
