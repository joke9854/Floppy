"""The legacy per-user API key is limited to the tracking preset over the REST API.

``User.token`` used to authenticate with ``request.auth is None``, which
``HasScope`` treated as full access. It now yields a credential holding
``LEGACY_TOKEN_SCOPES``. The webhook, Stremio and ListenBrainz-by-URL lookups
that read ``User.token`` outside DRF are unaffected.
"""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client as HttpClient
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from api import scopes
from api.authentication import LegacyKeyCredential, authenticate_token
from api.tests import test_listenbrainz as lbz
from api.tests.base import FloppyApiTestCase

CINETRACK_VIEWS = {
    "api.cinetrack_connection_views.CineTrackConnectionView": ("GET",),
    "api.views.MediaListView": ("GET",),
    "api.views.MediaDetailView": ("GET", "PATCH"),
    "api.fork_views_tracking.HistoryView": ("GET",),
    "api.fork_views_tracking.HistoryRecordView": ("DELETE",),
    "api.fork_views_tracking.MediaEpisodeEnsureView": ("POST",),
    "api.fork_views_tracking.CineTrackBootstrapMoviesEnsureView": ("POST",),
    "api.fork_views_tracking.CineTrackBootstrapShowsEnsureView": ("POST",),
    "api.fork_views_tracking.MediaEpisodeWatchView": ("POST",),
    "api.fork_views_tracking.MediaEpisodeDropView": ("POST",),
    "api.fork_views.TaskStatusView": ("GET",),
    "api.views.InfoView": ("GET",),
    "api.fork_views_watched_state.WatchedStateChangeFeedView": ("GET",),
    "api.listenbrainz_views.SubmitListensView": ("POST",),
}

SHOW = "/api/v1/media/tv/tmdb/1396"


class LegacyKeyScopeTests(FloppyApiTestCase):
    """What the legacy key can and cannot reach."""

    def setUp(self):
        """Send the user's real legacy key, not the shared full-access fixture."""
        super().setUp()
        self.legacy = {"HTTP_X_API_KEY": self.user1.token}

    def test_legacy_scopes_are_the_tracking_preset(self):
        """The limit is exactly the tracking preset."""
        self.assertEqual(scopes.LEGACY_TOKEN_SCOPES, scopes.TRACKING_PRESET)
        self.assertNotIn("*", scopes.LEGACY_TOKEN_SCOPES)

    def test_every_cinetrack_route_is_inside_the_limit(self):
        """No route CineTrack uses needs a scope the legacy key lacks."""
        for view, methods in CINETRACK_VIEWS.items():
            for method in methods:
                with self.subTest(view=view, method=method):
                    needed = scopes.VIEW_SCOPES[view][method]
                    self.assertTrue(
                        needed == scopes.ANY_SCOPE
                        or needed in scopes.LEGACY_TOKEN_SCOPES,
                        needed,
                    )

    def test_authenticate_token_returns_a_legacy_credential(self):
        """The legacy key is a credential object, never ``None``."""
        user, credential = authenticate_token(self.user1.token)
        self.assertEqual(user, self.user1)
        self.assertIsInstance(credential, LegacyKeyCredential)
        self.assertTrue(credential.has_scope("watchlist:read"))
        self.assertFalse(credential.has_scope("user:read"))
        self.assertFalse(credential.has_scope("imports:write"))

    def test_get_routes_cinetrack_uses_answer_200(self):
        """Read routes work with the legacy key."""
        for path in (
            "/api/v1/cinetrack/connection/",
            "/api/v1/info/",
            "/api/v1/media/",
            "/api/v1/history/",
            "/api/v1/collection/",
            "/api/v1/sync/changes/",
            "/api/v1/playback/progress/",
        ):
            with self.subTest(path=path):
                response = self.client.get(path, **self.legacy)
                self.assertEqual(response.status_code, HTTP.OK, response.content)

    def test_write_routes_cinetrack_uses_are_not_forbidden(self):
        """Write routes pass the permission check (bad input answers 4xx, not 403)."""
        calls = (
            ("get", f"{SHOW}/", None),
            ("patch", f"{SHOW}/", {}),
            ("delete", "/api/v1/history/movie/999999/", None),
            ("post", f"{SHOW}/episodes/ensure/", {"events": []}),
            ("post", "/api/v1/cinetrack/bootstrap/movies/ensure/", {"movies": []}),
            ("post", "/api/v1/cinetrack/bootstrap/shows/ensure/", {"shows": []}),
            ("post", f"{SHOW}/1/episodes/1/watch/", {}),
            ("post", f"{SHOW}/1/episodes/1/drop/", {}),
            ("get", "/api/v1/tasks/does-not-exist/", None),
        )
        for method, path, payload in calls:
            with self.subTest(method=method, path=path):
                kwargs = {} if payload is None else {"data": payload, "format": "json"}
                response = getattr(self.client, method)(
                    path,
                    **kwargs,
                    **self.legacy,
                )
                self.assertNotIn(
                    response.status_code,
                    (HTTP.FORBIDDEN, HTTP.UNAUTHORIZED),
                    response.content,
                )

    def test_legacy_key_cannot_read_user_settings(self):
        """user:read is outside the preset."""
        response = self.client.get("/api/v1/user/preferences/", **self.legacy)
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_legacy_key_cannot_start_imports(self):
        """imports:write is outside the preset."""
        response = self.client.post(
            "/api/v1/imports/trakt/",
            {},
            format="json",
            **self.legacy,
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_legacy_key_cannot_rotate_itself(self):
        """Credential management stays denied (NEVER)."""
        response = self.client.post("/api/v1/user/token/regenerate/", **self.legacy)
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.user1.refresh_from_db()
        self.assertEqual(self.legacy["HTTP_X_API_KEY"], self.user1.token)

    def test_legacy_key_works_as_bearer_and_token_schemes(self):
        """Every scheme the legacy key arrives by is held to the same limit."""
        for scheme in ("Bearer", "Token"):
            headers = {"HTTP_AUTHORIZATION": f"{scheme} {self.user1.token}"}
            with self.subTest(scheme=scheme):
                self.assertEqual(
                    self.client.get("/api/v1/collection/", **headers).status_code,
                    HTTP.OK,
                )
                self.assertEqual(
                    self.client.get("/api/v1/user/preferences/", **headers).status_code,
                    HTTP.FORBIDDEN,
                )

    def test_legacy_key_cannot_create_lists(self):
        """lists:write is outside the preset."""
        response = self.client.post(
            "/api/v1/lists/",
            {"name": "Mine"},
            format="json",
            **self.legacy,
        )
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)

    def test_session_style_access_is_still_full(self):
        """A request with no token object (session login) keeps full access."""
        client = APIClient()
        client.force_authenticate(user=self.user1)
        response = client.get("/api/v1/user/preferences/")
        self.assertEqual(response.status_code, HTTP.OK)


class LegacyKeyListenBrainzTests(lbz.ListenBrainzTestCase):
    """ListenBrainz submit maps to scrobble:write, which is in the preset."""

    def test_submit_with_the_legacy_token_still_works(self):
        """A legacy-token submit is accepted."""
        response = self.submit({"listen_type": "single", "payload": [lbz._listen()]})
        self.assertEqual(response.status_code, HTTP.OK, response.content)

    def test_validate_token_with_the_legacy_token_still_works(self):
        """validate-token answers for the legacy key."""
        response = self.client.get(lbz.VALIDATE_URL, **self.auth)
        self.assertEqual(response.status_code, HTTP.OK)


class LegacyKeyOutsideDrfTests(TestCase):
    """Webhook URLs carry the user token and are not limited by the REST preset."""

    def test_jellyfin_webhook_with_the_user_token_still_works(self):
        """The URL token authenticates the webhook as before."""
        user = get_user_model().objects.create_user(username="hook-user")
        url = reverse("jellyfin_webhook", kwargs={"token": user.token})
        with patch("integrations.views.tasks.process_webhook") as process:
            response = HttpClient().post(
                url,
                data={"Event": "Stop"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, HTTP.OK)
        process.delay.assert_called_once()
