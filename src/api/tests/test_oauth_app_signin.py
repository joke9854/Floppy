"""App sign-in: Floppy as an OAuth 2.0 / OpenID Connect provider.

Covers the built-in trusted apps, the authorization-code flow with PKCE, the
refresh and device grants, revocation, how app access tokens are enforced by
``HasScope``, and the Connected apps page. Accounts stay with allauth: anyone
not signed in is sent to allauth's login page first.
"""

import base64
import hashlib
from datetime import timedelta
from http import HTTPStatus as HTTP  # noqa: N814
from urllib.parse import parse_qs, urlencode, urlparse

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, DeviceGrant, RefreshToken

from api import scopes

AUTHORIZE = "/o/authorize/"
TOKEN = "/o/token/"
REVOKE = "/o/revoke_token/"
DEVICE_CODE = "/o/device-authorization/"
DEVICE_PAGE = "/o/device/"
DISCOVERY = "/o/.well-known/openid-configuration"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"
VERIFIER = "v" * 64
REDIRECT = "cinetrack://floppy"
COLLECTION = "/api/v1/collection/"
PREFERENCES = "/api/v1/user/preferences/"


def s256(verifier):
    """Return the S256 code challenge for ``verifier``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def form_post(client, url, data):
    """POST ``data`` form-encoded, as OAuth endpoints require."""
    return client.post(
        url,
        urlencode(data),
        content_type="application/x-www-form-urlencoded",
    )


def bearer(access_token):
    """Return request headers for a Bearer access token."""
    return {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}


def query_of(location):
    """Return the parsed query string of a redirect location."""
    return parse_qs(urlparse(location).query)


def make_access_token(user, client_id, raw, scope="openid watchlist:read"):
    """Store a live access token for ``user`` and the app ``client_id``."""
    return AccessToken.objects.create(
        user=user,
        application=Application.objects.get(client_id=client_id),
        token=raw,
        expires=timezone.now() + timedelta(hours=1),
        scope=scope,
    )


class SignInTestCase(TestCase):
    """Shared helpers for driving the sign-in flows."""

    def setUp(self):
        """Create a signed-in browser session for one user."""
        self.user = get_user_model().objects.create_user(
            username="oauth-user",
            password="pw-for-tests",
        )
        self.browser = HttpClient()
        self.browser.force_login(self.user)

    def authorize_params(self, **overrides):
        """Return a valid authorization request for the cinetrack app."""
        params = {
            "client_id": "cinetrack",
            "response_type": "code",
            "redirect_uri": REDIRECT,
            "scope": "openid watchlist:read",
            "state": "state-123",
            "code_challenge": s256(VERIFIER),
            "code_challenge_method": "S256",
        }
        params.update(overrides)
        return {key: value for key, value in params.items() if value is not None}

    def consent_form(self, **overrides):
        """Open the consent page and return its form."""
        params = self.authorize_params(**overrides)
        consent = self.browser.get(AUTHORIZE, params)
        self.assertEqual(consent.status_code, HTTP.OK)
        self.assertTemplateUsed(consent, "oauth2_provider/authorize.html")
        self.assertTemplateUsed(consent, "allauth/layouts/entrance.html")
        return params, consent.context["form"]

    def approve(self, allow=True, **overrides):
        """Show the consent page, answer it, and return the redirect response."""
        params, form = self.consent_form(**overrides)
        data = {key: value for key, value in form.initial.items() if value is not None}
        if allow:
            data["allow"] = "Authorize"
        return self.browser.post(f"{AUTHORIZE}?{urlencode(params)}", data)

    def code_from(self, response):
        """Extract the authorization code from a redirect response."""
        self.assertEqual(response.status_code, HTTP.FOUND)
        query = query_of(response["Location"])
        self.assertEqual(query["state"], ["state-123"], response["Location"])
        return query["code"][0]

    def exchange(self, code, **overrides):
        """Redeem an authorization code at the token endpoint."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT,
            "client_id": "cinetrack",
            "code_verifier": VERIFIER,
        }
        data.update(overrides)
        return form_post(
            HttpClient(),
            TOKEN,
            {key: value for key, value in data.items() if value is not None},
        )

    def sign_in(self, scope="openid watchlist:read"):
        """Run the whole flow and return the token response body."""
        code = self.code_from(self.approve(scope=scope))
        response = self.exchange(code)
        self.assertEqual(response.status_code, HTTP.OK, response.content)
        return response.json()


class BuiltInAppTests(TestCase):
    """The trusted apps exist after migrate."""

    def test_cinetrack_app(self):
        """CineTrack signs in with a custom-scheme redirect."""
        app = Application.objects.get(client_id="cinetrack")
        self.assertEqual(app.name, "CineTrack")
        self.assertEqual(app.redirect_uris, "cinetrack://floppy")
        self.assertEqual(app.authorization_grant_type, "authorization-code")

    def test_nuvio_apps(self):
        """Nuvio has its custom scheme and a loopback redirect, plus a TV app."""
        app = Application.objects.get(client_id="nuvio")
        self.assertEqual(app.name, "Nuvio")
        self.assertEqual(
            app.redirect_uris.split(),
            ["nuvio://floppy", "http://127.0.0.1/floppy"],
        )
        tv = Application.objects.get(client_id="nuvio-tv")
        self.assertEqual(tv.authorization_grant_type, DEVICE_GRANT)

    def test_shared_settings(self):
        """Every built-in app is public, asks for consent, and signs ID tokens."""
        for client_id in ("cinetrack", "nuvio", "nuvio-tv"):
            with self.subTest(app=client_id):
                app = Application.objects.get(client_id=client_id)
                self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
                self.assertFalse(app.skip_authorization)
                self.assertEqual(app.client_secret, "")
                self.assertEqual(app.algorithm, Application.RS256_ALGORITHM)

    def test_apps_may_request_identity_and_the_tracking_preset(self):
        """App scopes are openid plus the tracking preset, nothing broader."""
        self.assertEqual(scopes.APP_SCOPES, ("openid", *scopes.TRACKING_PRESET))
        self.assertNotIn("user:read", scopes.APP_SCOPES)

    def test_discovery_document(self):
        """Clients find every endpoint from the well-known document."""
        response = HttpClient().get(DISCOVERY)
        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertTrue(body["authorization_endpoint"].endswith(AUTHORIZE))
        self.assertTrue(body["token_endpoint"].endswith(TOKEN))
        jwks = HttpClient().get(urlparse(body["jwks_uri"]).path)
        self.assertEqual(jwks.status_code, HTTP.OK)

    def test_info_advertises_oauth(self):
        """/info/ tells a client this server supports app sign-in."""
        response = HttpClient().get("/api/v1/info/")
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertIs(response.json()["api_extensions"]["oauth_v1"], True)


class AuthorizationCodeFlowTests(SignInTestCase):
    """Authorization code with PKCE, end to end."""

    def test_full_flow_issues_tokens_that_hold_only_the_granted_scopes(self):
        """The access token reaches watchlist:read and nothing else."""
        body = self.sign_in()

        self.assertEqual(body["token_type"].lower(), "bearer")
        self.assertEqual(body["expires_in"], 7 * 24 * 60 * 60)
        self.assertIn("refresh_token", body)
        self.assertIn("id_token", body)

        ok = self.client.get(COLLECTION, **bearer(body["access_token"]))
        self.assertEqual(ok.status_code, HTTP.OK)
        denied = self.client.get(PREFERENCES, **bearer(body["access_token"]))
        self.assertEqual(denied.status_code, HTTP.FORBIDDEN)
        write = self.client.post(
            COLLECTION,
            {"media_type": "movie", "source": "tmdb", "media_id": "701"},
            format="json",
            **bearer(body["access_token"]),
        )
        self.assertEqual(write.status_code, HTTP.FORBIDDEN)

    def test_tokens_are_stored_as_checksums_only(self):
        """Neither the access nor the refresh token is kept in plaintext."""
        body = self.sign_in()
        access = AccessToken.objects.get(user=self.user)
        refresh = RefreshToken.objects.get(user=self.user)
        self.assertEqual(access.token, "")
        self.assertEqual(refresh.token, "")
        self.assertEqual(
            access.token_checksum,
            hashlib.sha256(body["access_token"].encode()).hexdigest(),
        )

    def test_authorization_response_names_the_issuer(self):
        """The redirect carries iss, matching the discovery document."""
        response = self.approve()
        issuer = HttpClient().get(DISCOVERY).json()["issuer"]
        self.assertEqual(query_of(response["Location"])["iss"], [issuer])

    def test_consent_is_always_shown(self):
        """approval_prompt=auto cannot skip consent, even after a sign-in."""
        self.sign_in()
        response = self.browser.get(
            AUTHORIZE,
            self.authorize_params(approval_prompt="auto"),
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertContains(response, "CineTrack")

    def test_anonymous_user_is_sent_to_the_allauth_login(self):
        """Nobody is authorized without signing in to Floppy first."""
        response = HttpClient().get(AUTHORIZE, self.authorize_params())
        self.assertEqual(response.status_code, HTTP.FOUND)
        self.assertTrue(
            response["Location"].startswith(reverse("account_login")),
            response["Location"],
        )

    def test_cancel_returns_access_denied(self):
        """Cancel sends the user back to the app with an error, not a code."""
        response = self.approve(allow=False)
        self.assertEqual(response.status_code, HTTP.FOUND)
        query = query_of(response["Location"])
        self.assertEqual(query["error"], ["access_denied"])
        self.assertNotIn("code", query)

    def test_missing_pkce_is_rejected(self):
        """A public app must send a code challenge."""
        response = self.browser.get(
            AUTHORIZE,
            self.authorize_params(code_challenge=None, code_challenge_method=None),
        )
        self.assertEqual(response.status_code, HTTP.FOUND)
        query = query_of(response["Location"])
        self.assertEqual(query["error"], ["invalid_request"])
        self.assertNotIn("code", query)

    def test_plain_challenge_method_is_rejected(self):
        """Only S256 is accepted; plain never yields a code."""
        response = self.approve(
            code_challenge=VERIFIER,
            code_challenge_method="plain",
        )
        self.assertEqual(response.status_code, HTTP.FOUND)
        query = query_of(response["Location"])
        self.assertEqual(query["error"], ["invalid_request"])
        self.assertNotIn("code", query)

    def test_missing_verifier_is_rejected(self):
        """The code cannot be redeemed without the verifier."""
        code = self.code_from(self.approve())
        response = self.exchange(code, code_verifier=None)
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertNotIn("access_token", response.json())

    def test_wrong_verifier_is_rejected(self):
        """A verifier that does not match the challenge fails."""
        code = self.code_from(self.approve())
        response = self.exchange(code, code_verifier="w" * 64)
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_code_is_single_use(self):
        """Redeeming a code twice fails the second time."""
        code = self.code_from(self.approve())
        self.assertEqual(self.exchange(code).status_code, HTTP.OK)
        self.assertEqual(self.exchange(code).status_code, HTTP.BAD_REQUEST)

    def test_unregistered_redirect_uri_is_rejected(self):
        """The user is never redirected to a URI the app did not register."""
        response = self.browser.get(
            AUTHORIZE,
            self.authorize_params(redirect_uri="https://evil.example/cb"),
        )
        self.assertNotIn("Location", response)
        self.assertIsNotNone(response.context["error"])

    def test_scope_outside_the_app_allowance_is_rejected(self):
        """An app cannot ask for user:read."""
        response = self.browser.get(
            AUTHORIZE,
            self.authorize_params(scope="openid user:read"),
        )
        self.assertEqual(response.status_code, HTTP.FOUND)
        self.assertEqual(query_of(response["Location"])["error"], ["invalid_scope"])

    def test_nuvio_loopback_redirect_ignores_the_port(self):
        """Nuvio may redirect to a loopback address on any port."""
        response = self.approve(
            client_id="nuvio",
            redirect_uri="http://127.0.0.1:41234/floppy",
        )
        self.assertEqual(response.status_code, HTTP.FOUND)
        location = urlparse(response["Location"])
        self.assertEqual(
            f"{location.scheme}://{location.netloc}{location.path}",
            "http://127.0.0.1:41234/floppy",
        )
        self.assertIn("code", parse_qs(location.query))


class RefreshAndRevokeTests(SignInTestCase):
    """Refresh rotation, reuse detection, revocation, and expiry."""

    def refresh(self, refresh_token):
        """Redeem a refresh token."""
        return form_post(
            HttpClient(),
            TOKEN,
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "cinetrack",
            },
        )

    def test_refresh_issues_a_new_access_token_and_rotates(self):
        """The refresh grant returns a working token and a new refresh token."""
        first = self.sign_in()
        response = self.refresh(first["refresh_token"])

        self.assertEqual(response.status_code, HTTP.OK, response.content)
        second = response.json()
        self.assertNotEqual(second["access_token"], first["access_token"])
        self.assertNotEqual(second["refresh_token"], first["refresh_token"])
        self.assertEqual(
            self.client.get(COLLECTION, **bearer(second["access_token"])).status_code,
            HTTP.OK,
        )

    def test_reusing_a_spent_refresh_token_ends_the_sign_in(self):
        """A spent refresh token is refused and revokes its successor too."""
        first = self.sign_in()
        second = self.refresh(first["refresh_token"]).json()

        self.assertEqual(
            self.refresh(first["refresh_token"]).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.refresh(second["refresh_token"]).status_code,
            HTTP.BAD_REQUEST,
        )

    def unused_for(self, days):
        """Pretend the last sign-in or refresh happened ``days`` days ago."""
        AccessToken.objects.filter(user=self.user).update(
            expires=timezone.now() - timedelta(days=days) + timedelta(days=7),
        )

    def test_refresh_token_lives_180_days_from_its_last_use(self):
        """Unused for 179 days it still works; unused for 181 days it does not."""
        first = self.sign_in()
        self.unused_for(179)
        second = self.refresh(first["refresh_token"])
        self.assertEqual(second.status_code, HTTP.OK, second.content)

        self.unused_for(181)
        self.assertEqual(
            self.refresh(second.json()["refresh_token"]).status_code,
            HTTP.BAD_REQUEST,
        )

    def test_app_drops_off_connected_apps_once_it_cannot_refresh(self):
        """After 180 unused days the app no longer shows as connected."""
        self.sign_in()
        self.unused_for(181)
        response = self.browser.get(reverse("integrations"))
        self.assertEqual(response.context["connected_apps"], [])

    def test_revoked_access_token_stops_working(self):
        """Revoking at the revocation endpoint ends API access at once."""
        body = self.sign_in()
        response = form_post(
            HttpClient(),
            REVOKE,
            {
                "token": body["access_token"],
                "token_type_hint": "access_token",
                "client_id": "cinetrack",
            },
        )
        self.assertEqual(response.status_code, HTTP.OK)

        # 403, like every dead credential: Floppy's authenticators send no
        # WWW-Authenticate challenge, so DRF reports an authentication failure
        # as 403 across the whole API (see test_nuvio_conformance step 8).
        after = self.client.get(COLLECTION, **bearer(body["access_token"]))
        self.assertEqual(after.status_code, HTTP.FORBIDDEN)

    def test_revoked_refresh_token_cannot_be_redeemed(self):
        """Revoking the refresh token prevents minting new access tokens."""
        body = self.sign_in()
        form_post(
            HttpClient(),
            REVOKE,
            {
                "token": body["refresh_token"],
                "token_type_hint": "refresh_token",
                "client_id": "cinetrack",
            },
        )
        self.assertEqual(
            self.refresh(body["refresh_token"]).status_code,
            HTTP.BAD_REQUEST,
        )

    def test_expired_access_token_is_refused(self):
        """An access token past its expiry no longer authenticates."""
        body = self.sign_in()
        AccessToken.objects.filter(user=self.user).update(
            expires=timezone.now() - timedelta(seconds=1),
        )
        response = self.client.get(COLLECTION, **bearer(body["access_token"]))
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_refresh_token_is_not_an_api_credential(self):
        """Only access tokens authenticate API calls."""
        body = self.sign_in()
        response = self.client.get(COLLECTION, **bearer(body["refresh_token"]))
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_deactivated_user_token_is_refused(self):
        """Disabling the account ends API access for its tokens."""
        body = self.sign_in()
        self.user.is_active = False
        self.user.save()
        response = self.client.get(COLLECTION, **bearer(body["access_token"]))
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)


class DeviceFlowTests(SignInTestCase):
    """RFC 8628 device authorization for TVs."""

    def start(self, client_id="nuvio-tv", scope="openid watchlist:read"):
        """Ask for a device code and return the response."""
        data = {"client_id": client_id}
        if scope:
            data["scope"] = scope
        return form_post(HttpClient(), DEVICE_CODE, data)

    def poll(self, device_code):
        """Poll the token endpoint once, past the polling interval."""
        DeviceGrant.objects.filter(device_code=device_code).update(
            last_checked=timezone.now() - timedelta(minutes=1),
        )
        return form_post(
            HttpClient(),
            TOKEN,
            {
                "grant_type": DEVICE_GRANT,
                "device_code": device_code,
                "client_id": "nuvio-tv",
            },
        )

    def enter_code(self, user_code):
        """Enter the user code in the browser and return the confirm page URL."""
        response = self.browser.post(DEVICE_PAGE, {"user_code": user_code})
        self.assertEqual(response.status_code, HTTP.FOUND)
        return response["Location"]

    def test_device_flow_end_to_end(self):
        """A TV gets a code, the user approves it in a browser, the TV polls."""
        started = self.start()
        self.assertEqual(started.status_code, HTTP.OK, started.content)
        device = started.json()
        self.assertIn("user_code", device)
        self.assertEqual(
            device["verification_uri"],
            f"http://testserver{DEVICE_PAGE}",
        )
        self.assertEqual(
            device["verification_uri_complete"],
            f"http://testserver{DEVICE_PAGE}?user_code={device['user_code']}",
        )

        pending = self.poll(device["device_code"])
        self.assertEqual(pending.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(pending.json()["error"], "authorization_pending")

        page = self.browser.get(DEVICE_PAGE, {"user_code": device["user_code"]})
        self.assertTemplateUsed(page, "allauth/layouts/entrance.html")
        confirm_url = self.enter_code(device["user_code"])
        confirm = self.browser.get(confirm_url)
        self.assertEqual(confirm.status_code, HTTP.OK)
        self.assertContains(confirm, "Nuvio (TV)")
        approved = self.browser.post(confirm_url, {"action": "accept"})
        self.assertEqual(approved.status_code, HTTP.FOUND)

        tokens = self.poll(device["device_code"])
        self.assertEqual(tokens.status_code, HTTP.OK, tokens.content)
        body = tokens.json()
        self.assertEqual(
            self.client.get(COLLECTION, **bearer(body["access_token"])).status_code,
            HTTP.OK,
        )
        self.assertEqual(
            self.client.get(PREFERENCES, **bearer(body["access_token"])).status_code,
            HTTP.FORBIDDEN,
        )
        self.assertEqual(AccessToken.objects.get().user, self.user)

    def test_denied_device_code_returns_no_tokens(self):
        """Denying in the browser ends the poll with access_denied."""
        device = self.start().json()
        confirm_url = self.enter_code(device["user_code"])
        self.browser.post(confirm_url, {"action": "deny"})

        response = self.poll(device["device_code"])
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(response.json()["error"], "access_denied")

    def test_device_flow_cannot_request_broader_scopes(self):
        """A TV cannot ask for user:read either."""
        response = self.start(scope="openid user:read")
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST, response.content)
        self.assertEqual(response.json()["error"], "invalid_scope")
        self.assertFalse(DeviceGrant.objects.exists())

    def test_device_code_without_scope_gets_the_app_defaults(self):
        """No scope means identity plus the tracking preset."""
        response = self.start(scope=None)
        self.assertEqual(response.status_code, HTTP.OK, response.content)
        self.assertEqual(
            DeviceGrant.objects.get().scope.split(),
            list(scopes.APP_SCOPES),
        )

    def test_phone_app_cannot_use_the_device_flow(self):
        """Only the TV app may start a device sign-in."""
        response = self.start(client_id="cinetrack")
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(response.json()["error"], "unauthorized_client")
        self.assertFalse(DeviceGrant.objects.exists())

    def test_unknown_app_cannot_use_the_device_flow(self):
        """An unregistered client_id gets invalid_client."""
        response = self.start(client_id="not-an-app")
        self.assertEqual(response.status_code, HTTP.UNAUTHORIZED)
        self.assertEqual(response.json()["error"], "invalid_client")
        self.assertFalse(DeviceGrant.objects.exists())

    def test_anonymous_user_is_sent_to_the_allauth_login(self):
        """Entering a device code needs a Floppy sign-in first."""
        response = HttpClient().get(DEVICE_PAGE)
        self.assertEqual(response.status_code, HTTP.FOUND)
        self.assertTrue(response["Location"].startswith(reverse("account_login")))


class ConnectedAppsTests(SignInTestCase):
    """The Connected apps list and its Revoke button."""

    def test_page_lists_the_signed_in_app(self):
        """The integrations page names the app and its scopes."""
        self.sign_in()
        response = self.browser.get(reverse("integrations"))
        self.assertEqual(response.status_code, HTTP.OK)
        apps = response.context["connected_apps"]
        self.assertEqual([app["name"] for app in apps], ["CineTrack"])
        self.assertEqual(sorted(apps[0]["scopes"]), ["openid", "watchlist:read"])
        self.assertContains(response, "Connected apps")
        self.assertContains(
            response,
            reverse("revoke_connected_app", args=["cinetrack"]),
        )

    def test_app_stays_listed_while_its_refresh_token_lives(self):
        """An expired access token does not hide an app that can still refresh."""
        self.sign_in()
        AccessToken.objects.filter(user=self.user).update(
            expires=timezone.now() - timedelta(seconds=1),
        )
        response = self.browser.get(reverse("integrations"))
        self.assertEqual(
            [app["name"] for app in response.context["connected_apps"]],
            ["CineTrack"],
        )

    def test_revoke_removes_only_this_users_grant(self):
        """Another user's tokens for the same app survive."""
        mine = self.sign_in()
        other_user = get_user_model().objects.create_user(username="someone-else")
        other = make_access_token(other_user, "cinetrack", "other-users-token")

        response = self.browser.post(
            reverse("revoke_connected_app", args=["cinetrack"]),
        )

        self.assertEqual(response.status_code, HTTP.FOUND)
        self.assertFalse(AccessToken.objects.filter(user=self.user).exists())
        self.assertFalse(RefreshToken.objects.filter(user=self.user).exists())
        self.assertTrue(AccessToken.objects.filter(pk=other.pk).exists())
        after = self.client.get(COLLECTION, **bearer(mine["access_token"]))
        self.assertEqual(after.status_code, HTTP.FORBIDDEN)

    def test_revoke_leaves_other_apps_connected(self):
        """Revoking CineTrack does not touch the user's Nuvio sign-in."""
        self.sign_in()
        nuvio = make_access_token(self.user, "nuvio", "nuvio-token")
        self.browser.post(reverse("revoke_connected_app", args=["cinetrack"]))
        self.assertTrue(AccessToken.objects.filter(pk=nuvio.pk).exists())

    def test_revoke_requires_post(self):
        """GET does not revoke."""
        self.sign_in()
        response = self.browser.get(
            reverse("revoke_connected_app", args=["cinetrack"]),
        )
        self.assertEqual(response.status_code, HTTP.METHOD_NOT_ALLOWED)
        self.assertTrue(AccessToken.objects.filter(user=self.user).exists())

    def test_revoke_is_csrf_protected(self):
        """A cross-site POST without the CSRF token is refused."""
        self.sign_in()
        browser = HttpClient(enforce_csrf_checks=True)
        browser.force_login(self.user)
        browser.post(reverse("revoke_connected_app", args=["cinetrack"]))
        # Floppy's CSRF failure view redirects; the point is nothing was revoked.
        self.assertTrue(AccessToken.objects.filter(user=self.user).exists())

    def test_revoke_of_an_app_the_user_never_connected_is_404(self):
        """There is nothing to revoke, and another user's grant is not revealed."""
        other_user = get_user_model().objects.create_user(username="someone-else")
        make_access_token(other_user, "nuvio", "other-nuvio-token")
        response = self.browser.post(reverse("revoke_connected_app", args=["nuvio"]))
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)
