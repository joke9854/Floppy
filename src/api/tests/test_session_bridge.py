"""v2 P3-B session bridge: the signed-in browser on /api/, allauth headless sign-in."""

import json
from http import HTTPStatus as HTTP  # noqa: N814

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.middleware.csrf import _get_new_csrf_string, _mask_cipher_secret
from django.test import Client, TestCase, override_settings

from integrations.models import IntegrationToken

ACCOUNT_URL = "/api/v1/user/account/"
ONBOARDING_URL = "/api/v1/user/onboarding/"
RECOVER_URL = "/api/v1/auth/password/recover/"
SESSION_URL = "/_allauth/browser/v1/auth/session"
LOGIN_URL = "/_allauth/browser/v1/auth/login"
PASSWORD = "a-long-test-password-1"


def _csrf_client(user=None):
    """A client that enforces CSRF like a browser, with a token at hand."""
    client = Client(enforce_csrf_checks=True)
    secret = _get_new_csrf_string()
    client.cookies["csrftoken"] = secret
    client.csrf_header = {"HTTP_X_CSRFTOKEN": _mask_cipher_secret(secret)}
    if user is not None:
        client.force_login(user)
    return client


class SessionOnApiTests(TestCase):
    """The browser session reaches the API; tokens keep their own rules."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="viewer", password=PASSWORD)

    def test_no_credentials_still_answer_403(self):
        # Unchanged by the session bridge: no credential at all is 403 (a
        # rejected Authorization header stays 401).
        response = Client().get(ACCOUNT_URL)

        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_a_session_reads_a_session_only_endpoint(self):
        response = _csrf_client(self.user).get(ACCOUNT_URL)

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["username"], "viewer")

    def test_a_session_write_needs_the_csrf_token(self):
        client = _csrf_client(self.user)
        body = json.dumps({"username": "viewer2"})

        refused = client.patch(ACCOUNT_URL, body, content_type="application/json")
        accepted = client.patch(
            ACCOUNT_URL,
            body,
            content_type="application/json",
            **client.csrf_header,
        )

        self.assertEqual(refused.status_code, HTTP.FORBIDDEN)
        self.assertEqual(accepted.status_code, HTTP.OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "viewer2")

    def test_a_token_is_judged_by_its_token_even_with_a_session_cookie(self):
        _token, raw = IntegrationToken.generate(
            user=self.user,
            name="onboarding",
            scopes=["user:read", "user:write"],
        )
        client = _csrf_client(self.user)

        # A token write needs no CSRF token.
        written = client.patch(
            ONBOARDING_URL,
            json.dumps({}),
            content_type="application/json",
            HTTP_X_API_KEY=raw,
        )
        # A session-only endpoint stays closed to the token.
        refused = client.get(ACCOUNT_URL, HTTP_X_API_KEY=raw)

        self.assertNotEqual(written.status_code, HTTP.FORBIDDEN)
        self.assertEqual(refused.status_code, HTTP.FORBIDDEN)


@override_settings(
    API_PASSWORD_RECOVERY_RATE_LIMIT="3/hour",
    API_PASSWORD_RECOVERY_ADDRESS_RATE_LIMIT="100/hour",
)
class PasswordRecoverTests(TestCase):
    """POST /api/v1/auth/password/recover/ (signed out)."""

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="lost", password=PASSWORD)
        self.codes = self.user.generate_recovery_codes()
        self.client = Client(enforce_csrf_checks=True)

    def tearDown(self):
        cache.clear()

    def _recover(self, **fields):
        body = {
            "username": "lost",
            "recovery_code": self.codes[0],
            "new_password1": "a-new-long-password-2",
            "new_password2": "a-new-long-password-2",
            **fields,
        }
        return self.client.post(RECOVER_URL, json.dumps(body), content_type="application/json")

    def test_a_recovery_code_sets_the_password_and_is_used_up(self):
        response = self._recover()

        self.assertEqual(response.status_code, HTTP.NO_CONTENT)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("a-new-long-password-2"))
        self.assertEqual(self._recover().status_code, HTTP.BAD_REQUEST)

    def test_a_wrong_code_and_an_unknown_user_get_the_same_answer(self):
        wrong_code = self._recover(recovery_code="DEADBEEF")
        unknown_user = self._recover(username="nobody")

        self.assertEqual(wrong_code.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(wrong_code.json(), unknown_user.json())
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_tries_per_username_are_limited(self):
        statuses = [self._recover(recovery_code="DEADBEEF").status_code for _ in range(4)]

        self.assertEqual(statuses[:3], [HTTP.BAD_REQUEST] * 3)
        self.assertEqual(statuses[3], HTTP.TOO_MANY_REQUESTS)

    def test_tokens_and_sessions_are_not_read(self):
        signed_in = _csrf_client(self.user)

        response = signed_in.post(
            RECOVER_URL,
            json.dumps({"username": "lost", "recovery_code": "DEADBEEF"}),
            content_type="application/json",
        )

        # Not 403 for a missing CSRF token: the session is not read at all.
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)


class HeadlessSignInTests(TestCase):
    """allauth headless, browser client, at /_allauth/."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(username="reader", password=PASSWORD)

    def test_signed_out_session_is_json_not_a_redirect(self):
        response = Client().get(SESSION_URL)

        self.assertEqual(response.status_code, HTTP.UNAUTHORIZED)
        self.assertEqual(response["Content-Type"].split(";")[0], "application/json")

    def test_sign_in_needs_csrf_then_opens_a_session_the_api_accepts(self):
        client = _csrf_client()
        body = json.dumps({"username": "reader", "password": PASSWORD})

        refused = client.post(LOGIN_URL, body, content_type="application/json")
        signed_in = client.post(LOGIN_URL, body, content_type="application/json", **client.csrf_header)
        account = client.get(ACCOUNT_URL)

        self.assertEqual(refused.status_code, HTTP.FORBIDDEN)
        self.assertEqual(signed_in.status_code, HTTP.OK)
        self.assertEqual(signed_in.json()["data"]["user"]["username"], "reader")
        self.assertEqual(account.status_code, HTTP.OK)

    def test_a_wrong_password_is_refused(self):
        client = _csrf_client()

        response = client.post(
            LOGIN_URL,
            json.dumps({"username": "reader", "password": "wrong-password"}),
            content_type="application/json",
            **client.csrf_header,
        )

        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)

    def test_routes_left_off_answer_404(self):
        client = _csrf_client(self.user)
        for route in (
            "account/password/change",
            "auth/password/request",
            "auth/password/reset",
            "account/email",
        ):
            response = client.post(
                f"/_allauth/browser/v1/{route}",
                "{}",
                content_type="application/json",
                **client.csrf_header,
            )
            self.assertEqual(response.status_code, HTTP.NOT_FOUND, route)

    def test_signup_stays_closed_once_an_account_exists(self):
        client = _csrf_client()

        response = client.post(
            "/_allauth/browser/v1/auth/signup",
            json.dumps({"username": "newcomer", "password": PASSWORD}),
            content_type="application/json",
            **client.csrf_header,
        )

        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertFalse(get_user_model().objects.filter(username="newcomer").exists())

    def test_sign_out_ends_the_session(self):
        client = _csrf_client(self.user)

        response = client.delete(SESSION_URL, **client.csrf_header)
        after = client.get(ACCOUNT_URL)

        self.assertEqual(response.status_code, HTTP.UNAUTHORIZED, response.content)
        self.assertEqual(after.status_code, HTTP.FORBIDDEN)
