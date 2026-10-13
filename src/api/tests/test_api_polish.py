"""API polish: request limits (429), error codes, and paging headers."""

from http import HTTPStatus as HTTP  # noqa: N814

from django.core.cache import cache
from django.test import override_settings

from integrations.models import IntegrationToken

from .base import FloppyApiTestCase

INFO = "/api/v1/info/"
COLLECTION = "/api/v1/collection/"
PROGRESS = "/api/v1/playback/progress/"


class RateLimitTests(FloppyApiTestCase):
    """Budgets per account and per address, read from settings."""

    def setUp(self):
        """Start every test with empty request counters."""
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)

    def get(self, url, headers=None):
        return self.client.get(url, **(headers if headers is not None else self.auth_headers))

    @override_settings(API_RATE_LIMIT="3/min")
    def test_past_the_budget_is_a_429_with_retry_after(self):
        """The fourth request in a minute is refused with a wait time."""
        for _ in range(3):
            self.assertEqual(self.get(COLLECTION).status_code, HTTP.OK)

        refused = self.get(COLLECTION)

        self.assertEqual(refused.status_code, HTTP.TOO_MANY_REQUESTS)
        retry_after = int(refused["Retry-After"])
        self.assertGreater(retry_after, 0)
        body = refused.json()
        self.assertEqual(body["code"], "throttled")
        self.assertEqual(body["retry_after"], retry_after)

    @override_settings(API_RATE_LIMIT="3/min")
    def test_the_budget_is_shared_by_an_accounts_keys(self):
        """A second key of the same account draws from the same budget."""
        _, other_key = IntegrationToken.generate(
            user=self.user1, name="second app", scopes=["*"]
        )
        self.get(COLLECTION)
        self.get(COLLECTION)
        self.get(COLLECTION, {"HTTP_X_API_KEY": other_key})

        refused = self.get(COLLECTION, {"HTTP_X_API_KEY": other_key})
        self.assertEqual(refused.status_code, HTTP.TOO_MANY_REQUESTS)

    @override_settings(API_RATE_LIMIT="3/min")
    def test_accounts_have_separate_budgets(self):
        """One busy account does not slow another down."""
        for _ in range(4):
            self.get(COLLECTION)
        self.assertEqual(self.get(COLLECTION, self.auth_headers2).status_code, HTTP.OK)

    @override_settings(API_ANON_RATE_LIMIT="2/min", API_RATE_LIMIT=None)
    def test_requests_without_credentials_have_their_own_budget(self):
        """Public endpoints are limited per address."""
        self.assertEqual(self.get(INFO, {}).status_code, HTTP.OK)
        self.assertEqual(self.get(INFO, {}).status_code, HTTP.OK)
        self.assertEqual(self.get(INFO, {}).status_code, HTTP.TOO_MANY_REQUESTS)
        # Signed-in requests are not counted against the anonymous budget.
        # (/info/ itself is public and never reads credentials.)
        self.assertEqual(self.get(COLLECTION).status_code, HTTP.OK)

    @override_settings(API_RATE_LIMIT=None, API_ANON_RATE_LIMIT=None)
    def test_no_rate_means_no_limit(self):
        """A self-hoster can turn the limits off."""
        for _ in range(20):
            self.assertEqual(self.get(COLLECTION).status_code, HTTP.OK)


class ErrorCodeTests(FloppyApiTestCase):
    """Every ``{"detail": ...}`` error names a machine-readable code."""

    def test_missing_credentials(self):
        """DRF's own errors keep their code."""
        response = self.client.get(COLLECTION)
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertEqual(response.json()["code"], "not_authenticated")

    def test_invalid_credentials(self):
        """A bad key is an authentication failure."""
        response = self.client.get(COLLECTION, **self.invalid_auth_headers)
        self.assertEqual(response.json()["code"], "authentication_failed")

    def test_missing_scope(self):
        """A key without the scope is a permission error."""
        _, narrow_key = IntegrationToken.generate(
            user=self.user1, name="narrow", scopes=["catalog:read"]
        )
        response = self.client.get(COLLECTION, HTTP_X_API_KEY=narrow_key)
        self.assertEqual(response.status_code, HTTP.FORBIDDEN)
        self.assertEqual(response.json()["code"], "permission_denied")

    def test_hand_built_errors_get_a_code_from_their_status(self):
        """A view's own 400 says bad_request."""
        response = self.client.get("/api/v1/search/id/", **self.auth_headers)
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {"detail": "Give exactly one of imdb, tmdb, or tvdb.", "code": "bad_request"},
        )

    def test_field_errors_are_left_alone(self):
        """Validation bodies keyed by field get no extra key."""
        response = self.client.patch(
            "/api/v1/user/preferences/",
            {"scrobble_watched_percent": 42},
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        body = response.json()
        if "detail" not in body:
            self.assertNotIn("code", body)

    def test_success_bodies_are_unchanged(self):
        """Only errors get a code."""
        response = self.client.get(INFO)
        self.assertNotIn("code", response.json())


class PagingHeaderTests(FloppyApiTestCase):
    """A ``pagination`` envelope is mirrored into headers."""

    def put_progress(self, media_id, position):
        response = self.client.put(
            PROGRESS,
            {
                "media_type": "movie",
                "ids": {"tmdb": media_id},
                "position_seconds": position,
            },
            format="json",
            **self.auth_headers,
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)

    def test_headers_match_the_body(self):
        """Item count, limit, offset and Link next/prev."""
        self.put_progress("701", 100)
        self.put_progress("702", 200)
        self.put_progress("703", 300)

        response = self.client.get(
            PROGRESS,
            {"limit": 1, "offset": 1},
            **self.auth_headers,
        )

        self.assertEqual(response.status_code, HTTP.OK)
        pagination = response.json()["pagination"]
        self.assertEqual(response["X-Pagination-Item-Count"], str(pagination["total"]))
        self.assertEqual(response["X-Pagination-Limit"], "1")
        self.assertEqual(response["X-Pagination-Offset"], "1")
        self.assertEqual(
            response["Link"],
            f'<{pagination["next"]}>; rel="next", <{pagination["previous"]}>; rel="prev"',
        )

    def test_first_page_has_no_prev_link(self):
        """Only the links that exist are sent."""
        self.put_progress("701", 100)
        self.put_progress("702", 200)

        response = self.client.get(PROGRESS, {"limit": 1}, **self.auth_headers)

        self.assertIn('rel="next"', response["Link"])
        self.assertNotIn('rel="prev"', response["Link"])

    def test_unpaginated_responses_have_no_paging_headers(self):
        """Plain bodies are untouched."""
        response = self.client.get(INFO)
        self.assertNotIn("X-Pagination-Item-Count", response)
        self.assertNotIn("Link", response)
