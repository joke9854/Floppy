from django.contrib import auth
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from users import helpers


@override_settings(
    REGISTRATION=True,
    ACCOUNT_ADAPTER="allauth.account.adapter.DefaultAccountAdapter",
)
class SignupViewTests(TestCase):
    """Test the local registration flow at account_signup with sign-up open."""

    def setUp(self):
        """Clear the cached first-run flag so it doesn't leak between tests."""
        cache.delete(helpers.IS_FIRST_RUN_CACHE_KEY)

    def test_fresh_registration_succeeds(self):
        """Test a brand-new installation can register a local account."""
        response = self.client.post(
            reverse("account_signup"),
            {
                "username": "newuser",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
            },
        )

        self.assertNotEqual(response.status_code, 500)
        self.assertTrue(
            get_user_model().objects.filter(username="newuser").exists(),
        )
        self.assertEqual(auth.get_user(self.client).username, "newuser")

    def test_new_account_starts_on_cinetrack_with_tv_movies_and_anime(self):
        """Test a new account gets the W6 theme and media-type defaults."""
        existing = get_user_model().objects.create_user(
            username="existing",
            password="12345",
        )

        self.client.post(
            reverse("account_signup"),
            {
                "username": "newuser",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
            },
        )

        user = get_user_model().objects.get(username="newuser")
        self.assertEqual(user.theme, "cinetrack")
        self.assertEqual(
            user.get_enabled_media_types(),
            ["tv", "season", "movie", "anime"],
        )
        existing.refresh_from_db()
        self.assertEqual(existing.theme, "system")
        self.assertTrue(existing.book_enabled)

    def test_duplicate_username_returns_form_error_not_500(self):
        """Test registering an already-taken username re-renders with an error."""
        get_user_model().objects.create_user(username="taken", password="12345")

        response = self.client.post(
            reverse("account_signup"),
            {
                "username": "taken",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            get_user_model().objects.filter(username="taken", is_active=True).count()
            > 1,
        )
        self.assertFormError(
            response.context["form"],
            "username",
            "A user with that username already exists.",
        )

    def test_first_run_shows_welcome_copy(self):
        """Test the signup page greets a fresh install differently."""
        response = self.client.get(reverse("account_signup"))

        self.assertContains(response, "Welcome to Floppy")

    def test_not_first_run_after_a_real_account_exists(self):
        """Test the welcome copy disappears once a real account exists."""
        get_user_model().objects.create_user(username="existing", password="12345")
        cache.delete(helpers.IS_FIRST_RUN_CACHE_KEY)

        response = self.client.get(reverse("account_signup"))

        self.assertNotContains(response, "Welcome to Floppy")


class ClosedRegistrationDefaultTests(TestCase):
    """REGISTRATION defaults to off, but a fresh install can still set up."""

    def setUp(self):
        """Clear the cached first-run flag so it doesn't leak between tests."""
        cache.delete(helpers.IS_FIRST_RUN_CACHE_KEY)

    def _signup(self, username):
        return self.client.post(
            reverse("account_signup"),
            {
                "username": username,
                "password1": "a-very-strong-pass123",
                "password2": "a-very-strong-pass123",
            },
        )

    def test_first_account_can_sign_up_then_signup_closes(self):
        """The first real account signs up; the next visitor is turned away."""
        login_page = self.client.get(reverse("account_login"))
        self.assertContains(login_page, "Create your account")

        self._signup("owner")
        self.assertTrue(get_user_model().objects.filter(username="owner").exists())

        self.client.logout()
        # The cached first-run flag is still True here; the adapter must not
        # rely on it.
        self._signup("stranger")
        self.assertFalse(
            get_user_model().objects.filter(username="stranger").exists(),
        )

    def test_login_page_hides_signup_once_an_account_exists(self):
        """With sign-up closed, the login page offers no sign-up link."""
        get_user_model().objects.create_user(username="existing", password="12345")

        response = self.client.get(reverse("account_login"))

        self.assertNotContains(response, reverse("account_signup"))
