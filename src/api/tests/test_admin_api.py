"""FORK (P1-I): instance administration and maintenance, session logins only."""

from http import HTTPStatus as HTTP  # noqa: N814
from unittest.mock import patch

from app.models import Movie
from integrations.models import ImportRun, IntegrationToken

from .base import FloppyApiTestCase


class SessionCase(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_authenticate(user=self.user1)
        self.addCleanup(self.client.force_authenticate, user=None)

    def promote(self):
        self.user1.is_superuser = True
        self.user1.save(update_fields=["is_superuser"])


class ProviderTests(SessionCase):
    def test_providers_list_masks_values(self):
        response = self.call_api("get", "api_metadata_providers")
        self.assertEqual(response.status_code, HTTP.OK)
        body = response.json()
        self.assertFalse(body["can_edit_instance"])
        slugs = {p["slug"] for group in body["groups"] for p in group["providers"]}
        self.assertIn("tmdb", slugs)

    @patch("app.providers.credentials.set_instance")
    def test_instance_credentials_need_a_superuser(self, set_instance):
        denied = self.call_api(
            "put", "api_provider_instance_credentials", args=("tmdb",), payload={}
        )
        self.assertEqual(denied.status_code, HTTP.FORBIDDEN)
        set_instance.assert_not_called()

        self.promote()
        self.assertEqual(
            self.call_api(
                "put", "api_provider_instance_credentials", args=("nope",), payload={}
            ).status_code,
            HTTP.NOT_FOUND,
        )

    def test_default_provider(self):
        bad = self.call_api(
            "put", "api_default_provider", args=("tv",), payload={"source": "nope"}
        )
        self.assertEqual(bad.status_code, HTTP.BAD_REQUEST)
        response = self.call_api(
            "put", "api_default_provider", args=("tv",), payload={"source": "tmdb"}
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            self.call_api(
                "put", "api_default_provider", args=("movie",), payload={"source": "tmdb"}
            ).status_code,
            HTTP.NOT_FOUND,
        )


class InstanceSettingsTests(SessionCase):
    @patch("app.image_cache.set_enabled")
    def test_image_cache_needs_a_superuser(self, set_enabled):
        self.assertEqual(self.call_api("get", "api_admin_image_cache").status_code, HTTP.OK)
        denied = self.call_api("patch", "api_admin_image_cache", payload={"enabled": True})
        self.assertEqual(denied.status_code, HTTP.FORBIDDEN)
        self.promote()
        ok = self.call_api("patch", "api_admin_image_cache", payload={"enabled": True})
        self.assertEqual(ok.status_code, HTTP.OK)
        set_enabled.assert_called_once_with(True)
        bad = self.call_api("patch", "api_admin_image_cache", payload={"days": 9})
        self.assertEqual(bad.status_code, HTTP.BAD_REQUEST)

    def test_logs_and_server_port_need_a_superuser(self):
        self.assertEqual(self.call_api("get", "api_admin_logs").status_code, HTTP.FORBIDDEN)
        self.assertEqual(
            self.call_api("put", "api_admin_server_port", payload={"port": 8080}).status_code,
            HTTP.FORBIDDEN,
        )
        self.assertEqual(self.call_api("get", "api_admin_server_port").status_code, HTTP.OK)


class MaintenanceTests(SessionCase):
    def test_tmdb_proxy_is_stored_encrypted_and_never_returned(self):
        response = self.call_api(
            "put", "api_user_tmdb_proxy", payload={"url": "https://proxy.example:8080"}
        )
        self.assertEqual(response.json(), {"configured": True})
        self.user1.refresh_from_db()
        self.assertNotIn("proxy.example", self.user1.tmdb_proxy_url)
        self.assertEqual(
            self.call_api("put", "api_user_tmdb_proxy", payload={"url": "ftp://x"}).status_code,
            HTTP.BAD_REQUEST,
        )
        self.assertEqual(
            self.call_api("delete", "api_user_tmdb_proxy").status_code, HTTP.NO_CONTENT
        )

    def test_clear_caches(self):
        response = self.call_api(
            "post", "api_user_caches_clear", payload={"caches": ["history"]}
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(list(response.json()["cleared"]), ["history"])
        self.assertEqual(
            self.call_api(
                "post", "api_user_caches_clear", payload={"caches": ["everything"]}
            ).status_code,
            HTTP.BAD_REQUEST,
        )

    def test_bulk_delete_needs_confirmation(self):
        count = Movie.objects.filter(user=self.user1).count()
        others = Movie.objects.exclude(user=self.user1).count()
        self.assertGreater(count, 0)
        unconfirmed = self.call_api(
            "post", "api_library_bulk_delete", payload={"media_type": "movie"}
        )
        self.assertEqual(unconfirmed.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(Movie.objects.filter(user=self.user1).count(), count)

        deleted = self.call_api(
            "post",
            "api_library_bulk_delete",
            payload={"media_type": "movie", "confirm": "movie"},
        )
        self.assertEqual(deleted.status_code, HTTP.OK)
        self.assertEqual(deleted.json()["deleted"], count)
        self.assertFalse(Movie.objects.filter(user=self.user1).exists())
        self.assertEqual(Movie.objects.exclude(user=self.user1).count(), others)

    def test_bulk_delete_by_import_source(self):
        run = ImportRun.objects.create(
            user=self.user1, source="trakt", status=ImportRun.Status.COMPLETED
        )
        Movie.objects.filter(id=self.movie_medias[0].id).update(import_run=run)
        summary = self.call_api("get", "api_library_bulk_delete").json()
        self.assertIn(
            {"media_type": "movie", "source": "trakt", "count": 1},
            summary["import_sources"],
        )
        response = self.call_api(
            "post",
            "api_library_bulk_delete",
            payload={"media_type": "movie", "confirm": "movie", "source": "trakt"},
        )
        self.assertEqual(response.status_code, HTTP.OK, response.content)
        self.assertEqual(response.json()["deleted"], 1)
        self.assertFalse(Movie.objects.filter(id=self.movie_medias[0].id).exists())
        self.assertTrue(Movie.objects.filter(user=self.user1).exists())


class TokenDenialTests(FloppyApiTestCase):
    def test_no_token_reaches_administration(self):
        _, raw = IntegrationToken.generate(user=self.user1, name="w", scopes=["*"])
        headers = {"HTTP_X_API_KEY": raw}
        for method, name, args in (
            ("get", "api_metadata_providers", ()),
            ("put", "api_provider_personal_credentials", ("tmdb",)),
            ("put", "api_default_provider", ("tv",)),
            ("get", "api_admin_logs", ()),
            ("post", "api_admin_image_cache_clear", ()),
            ("put", "api_user_tmdb_proxy", ()),
            ("post", "api_user_caches_clear", ()),
            ("post", "api_library_bulk_delete", ()),
        ):
            with self.subTest(name=name, method=method):
                response = self.call_api(
                    method, name, args=args, payload={}, headers=headers
                )
                self.assertEqual(response.status_code, HTTP.FORBIDDEN)
