"""FORK (P1-G): account and credential management, session logins only."""

import hashlib
from datetime import timedelta
from http import HTTPStatus as HTTP  # noqa: N814

from django.urls import reverse
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application, RefreshToken

from api import scopes as api_scopes
from integrations.models import CatalogGrant, IntegrationToken

from .base import FloppyApiTestCase

ALL_SCOPES = " ".join(sorted(api_scopes.ALL_SCOPES))


class SessionTestCase(FloppyApiTestCase):
    """Calls made as a signed-in session (no token object on the request)."""

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user1)
        self.addCleanup(self.client.force_authenticate, user=None)

    def call(self, method, name, args=(), payload=None):
        return self.call_api(method, name, args=args, payload=payload)


class TokenTests(SessionTestCase):
    def test_create_returns_the_secret_once_and_lists_without_it(self):
        response = self.call(
            "post",
            "api_user_tokens",
            payload={
                "name": "Kodi",
                "scopes": ["watchlist:read", "scrobble:write"],
                "expires_in_days": 30,
            },
        )

        self.assertEqual(response.status_code, HTTP.CREATED)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        secret = body["secret"]
        token = IntegrationToken.objects.get(id=body["id"])
        self.assertEqual(
            token.token_digest, hashlib.sha256(secret.encode()).hexdigest()
        )
        self.assertEqual(token.scopes, ["watchlist:read", "scrobble:write"])
        self.assertIsNotNone(token.expires_at)

        listed = self.call("get", "api_user_tokens")
        self.assertEqual(listed.status_code, HTTP.OK)
        self.assertNotIn(secret, listed.content.decode())
        self.assertNotIn(token.token_digest, listed.content.decode())
        self.assertIn(body["id"], [t["id"] for t in listed.json()["results"]])
        self.assertTrue(listed.json()["scope_choices"])

        # The new token works, scoped.
        self.client.force_authenticate(user=None)
        self.assertEqual(
            self.call_api(
                "get", "api_user_preferences", headers={"HTTP_X_API_KEY": secret}
            ).status_code,
            HTTP.FORBIDDEN,
        )

    def test_bad_requests(self):
        for payload in (
            {"name": "", "scopes": ["watchlist:read"]},
            {"name": "x", "scopes": []},
            {"name": "x", "scopes": ["root:all"]},
            {"name": "x", "scopes": "watchlist:read"},
            {"name": "x", "scopes": ["watchlist:read"], "expires_in_days": 0},
            {"name": "x", "scopes": ["watchlist:read"], "expires_in_days": "soon"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.call("post", "api_user_tokens", payload=payload).status_code,
                    HTTP.BAD_REQUEST,
                )

    def test_revoke_own_token_only(self):
        mine, _ = IntegrationToken.generate(user=self.user1, name="mine", scopes=["*"])
        theirs, _ = IntegrationToken.generate(
            user=self.user2, name="theirs", scopes=["*"]
        )

        self.assertEqual(
            self.call("delete", "api_user_token_detail", args=(theirs.id,)).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self.call("delete", "api_user_token_detail", args=(mine.id,)).status_code,
            HTTP.NO_CONTENT,
        )
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertIsNotNone(mine.revoked_at)
        self.assertIsNone(theirs.revoked_at)


class CatalogGrantTests(SessionTestCase):
    def test_create_list_and_revoke(self):
        response = self.call(
            "post",
            "api_user_catalog_grants",
            payload={"name": "Living room", "allow_playback_start": False},
        )

        self.assertEqual(response.status_code, HTTP.CREATED)
        self.assertEqual(response["Cache-Control"], "no-store")
        body = response.json()
        grant = CatalogGrant.objects.get(id=body["id"])
        self.assertFalse(grant.allow_playback_start)
        self.assertTrue(
            body["manifest_url"].endswith(
                reverse("stremio_addon_manifest", args=[grant.token])
            )
        )
        listed = self.call("get", "api_user_catalog_grants").content.decode()
        self.assertNotIn(grant.token, listed)

        other = CatalogGrant.generate(user=self.user2, name="theirs")[0]
        self.assertEqual(
            self.call(
                "delete", "api_user_catalog_grant_detail", args=(other.id,)
            ).status_code,
            HTTP.NOT_FOUND,
        )
        self.assertEqual(
            self.call(
                "delete", "api_user_catalog_grant_detail", args=(grant.id,)
            ).status_code,
            HTTP.NO_CONTENT,
        )
        grant.refresh_from_db()
        self.assertIsNotNone(grant.revoked_at)

    def test_name_is_required(self):
        response = self.call("post", "api_user_catalog_grants", payload={"name": " "})
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)


class ConnectedAppTests(SessionTestCase):
    def setUp(self):
        super().setUp()
        app = Application.objects.get(client_id="nuvio")
        access = AccessToken.objects.create(
            user=self.user1,
            application=app,
            token="access-1",
            expires=timezone.now() + timedelta(hours=1),
            scope="openid watchlist:read",
        )
        self.refresh = RefreshToken.objects.create(
            user=self.user1, application=app, token="refresh-1", access_token=access
        )

    def test_list_sign_out_one_install_and_disconnect(self):
        listed = self.call("get", "api_user_connected_apps").json()
        self.assertEqual([app["client_id"] for app in listed["apps"]], ["nuvio"])
        session_id = listed["sessions"][0]["id"]
        self.assertEqual(session_id, f"r{self.refresh.id}")
        self.assertNotIn("refresh-1", str(listed))
        self.assertNotIn("access-1", str(listed))

        self.assertEqual(
            self.call(
                "delete", "api_user_app_session_detail", args=(session_id,)
            ).status_code,
            HTTP.NO_CONTENT,
        )
        self.refresh.refresh_from_db()
        self.assertIsNotNone(self.refresh.revoked)
        self.assertEqual(
            self.call(
                "delete", "api_user_app_session_detail", args=(session_id,)
            ).status_code,
            HTTP.NOT_FOUND,
        )

        AccessToken.objects.create(
            user=self.user1,
            application=Application.objects.get(client_id="nuvio"),
            token="access-2",
            expires=timezone.now() + timedelta(hours=1),
            scope="openid",
        )
        self.assertEqual(
            self.call(
                "delete", "api_user_connected_app_detail", args=("nuvio",)
            ).status_code,
            HTTP.NO_CONTENT,
        )
        self.assertFalse(AccessToken.objects.filter(user=self.user1).exists())
        self.assertEqual(
            self.call(
                "delete", "api_user_connected_app_detail", args=("nuvio",)
            ).status_code,
            HTTP.NOT_FOUND,
        )


class AccountTests(SessionTestCase):
    def test_change_username(self):
        response = self.call("patch", "api_user_account", payload={"username": "renamed"})
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["username"], "renamed")
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.username, "renamed")

        taken = self.call(
            "patch", "api_user_account", payload={"username": self.user2.username}
        )
        self.assertEqual(taken.status_code, HTTP.BAD_REQUEST)
        self.assertIn("username", taken.json()["errors"])

    def test_change_password_checks_the_current_one(self):
        self.user1.set_password("old-pass-123")
        self.user1.save()
        wrong = self.call(
            "post",
            "api_user_password",
            payload={
                "old_password": "nope",
                "new_password1": "A-much-better-pass-9",
                "new_password2": "A-much-better-pass-9",
            },
        )
        self.assertEqual(wrong.status_code, HTTP.BAD_REQUEST)
        self.assertIn("old_password", wrong.json()["errors"])
        self.assertNotIn("A-much-better-pass-9", wrong.content.decode())

        changed = self.call(
            "post",
            "api_user_password",
            payload={
                "old_password": "old-pass-123",
                "new_password1": "A-much-better-pass-9",
                "new_password2": "A-much-better-pass-9",
            },
        )
        self.assertEqual(changed.status_code, HTTP.NO_CONTENT)
        self.user1.refresh_from_db()
        self.assertTrue(self.user1.check_password("A-much-better-pass-9"))


class NoTokenMayManageCredentialsTests(FloppyApiTestCase):
    """Every credential endpoint is closed to every kind of token."""

    CASES = (
        ("get", "api_user_account", ()),
        ("patch", "api_user_account", ()),
        ("post", "api_user_password", ()),
        ("get", "api_user_tokens", ()),
        ("post", "api_user_tokens", ()),
        ("delete", "api_user_token_detail", (1,)),
        ("get", "api_user_catalog_grants", ()),
        ("post", "api_user_catalog_grants", ()),
        ("delete", "api_user_catalog_grant_detail", (1,)),
        ("get", "api_user_connected_apps", ()),
        ("delete", "api_user_connected_app_detail", ("nuvio",)),
        ("delete", "api_user_app_session_detail", ("r1",)),
    )

    def _credentials(self):
        _, wildcard = IntegrationToken.generate(user=self.user1, name="w", scopes=["*"])
        AccessToken.objects.create(
            user=self.user1,
            application=Application.objects.get(client_id="cinetrack"),
            token="oauth-everything",
            expires=timezone.now() + timedelta(hours=1),
            scope=f"openid {ALL_SCOPES}",
        )
        return {
            "wildcard token": {"HTTP_X_API_KEY": wildcard},
            "legacy key": {"HTTP_X_API_KEY": self.user1.token},
            "oauth bearer": {"HTTP_AUTHORIZATION": "Bearer oauth-everything"},
        }

    def test_every_token_kind_gets_403(self):
        for label, headers in self._credentials().items():
            for method, name, args in self.CASES:
                with self.subTest(credential=label, endpoint=name, method=method):
                    response = self.call_api(
                        method, name, args=args, payload={}, headers=headers
                    )
                    self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertEqual(
            IntegrationToken.objects.filter(user=self.user1).count(),
            # base fixture token + the wildcard above
            2,
        )


class OnboardingTests(FloppyApiTestCase):
    def _call(self, method, payload=None):
        return self.call_api(
            method, "api_user_onboarding", payload=payload, headers=self.auth_headers
        )

    def test_read_and_advance_the_wizard(self):
        state = self._call("get").json()
        slugs = [source["slug"] for source in state["sources"]]
        self.assertIn("yamtrack", slugs)
        self.assertIn("in_progress", state["choices"]["status"])

        response = self._call(
            "patch",
            {
                "status": "in_progress",
                "step": "services_summary",
                "selected_sources": ["yamtrack", "yamtrack"],
            },
        )

        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertEqual(body["selected_sources"], ["yamtrack"])
        self.assertEqual(body["remaining_sources"], ["yamtrack"])
        self.user1.refresh_from_db()
        self.assertEqual(self.user1.onboarding_step, "services_summary")

        skipped = self._call("patch", {"skipped_sources": ["yamtrack"]}).json()
        self.assertEqual(skipped["remaining_sources"], [])

    def test_unknown_values_are_400(self):
        for payload in (
            {"status": "nope"},
            {"step": "nope"},
            {"selected_sources": ["not-a-source"]},
            {"skipped_integrations": "plex"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self._call("patch", payload).status_code, HTTP.BAD_REQUEST)
