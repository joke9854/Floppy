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

    def test_cinetrack_rows_keep_the_card_endpoints_and_ids(self):
        classic = self.client.get(reverse("history")).content.decode()
        self._use_cinetrack()
        cinetrack = self.client.get(reverse("history")).content.decode()

        for marker in ('hx-target="#track-', 'hx-target="#lists-', 'id="track-', 'id="lists-', 'id="history-day-'):
            self.assertEqual(classic.count(marker), cinetrack.count(marker), marker)

    def test_classic_history_keeps_the_cards(self):
        response = self.client.get(reverse("history"))

        self.assertTemplateNotUsed(response, "app/components/ct/history_day.html")
        self.assertContains(response, "media-card bg-")
        self.assertNotContains(response, "ct-history-row")
        self.assertNotContains(response, "htmx.swap(page")
        self.assertNotContains(response, "data-ct-page")


class CineTrackPageShellTests(_ThemeMixin, TestCase):
    """W5: Calendar, Stats, Lists and Settings restyle only under the ct theme."""

    def test_calendar_adds_the_phone_agenda(self):
        self._use_cinetrack()

        response = self.client.get(reverse("calendar"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ct-calendar")
        self.assertContains(response, 'class="ct-cal-mode md:hidden"')
        self.assertContains(response, 'class="ct-agenda"')

    def test_classic_calendar_is_unchanged(self):
        response = self.client.get(reverse("calendar"))

        self.assertNotContains(response, "ct-calendar")
        self.assertNotContains(response, "ct-agenda")

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

    def test_classic_pages_have_no_ct_marker(self):
        for name in ("statistics", "lists", "account"):
            with self.subTest(name=name):
                response = self.client.get(reverse(name))
                self.assertNotContains(response, "data-ct-page")
                self.assertNotContains(response, "ct-settings")
                self.assertNotContains(response, "ct-fab")


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
        classic = self._authorize()
        self._use_cinetrack()
        cinetrack = self._authorize()

        self.assertEqual(cinetrack.status_code, 200)
        self.assertTemplateUsed(cinetrack, "oauth2_provider/authorize.html")
        self.assertNotContains(classic, "ct-entrance")
        self.assertContains(cinetrack, "ct-entrance")
        self.assertContains(cinetrack, 'id="authorizationForm"')
        self.assertContains(cinetrack, 'name="allow"')
        self.assertEqual(
            sorted(classic.context["form"].fields),
            sorted(cinetrack.context["form"].fields),
        )

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
