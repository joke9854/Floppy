"""FORK (P1-D): move a tracked show; migrate flat MAL anime to grouped."""

from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.db import OperationalError

from app.models import Item, MediaTypes, Sources
from app.providers import services
from app.services import anime_migration, library_migration

from .base import FloppyApiTestCase

MIGRATE = "app.services.library_migration.migrate_library_item"


def _raise_from_provider(message):
    """Raise the service error the way the service does: inside the provider's except."""
    error = library_migration.LibraryMigrationError(message)
    error.__context__ = services.ProviderAPIError(
        "tmdb", requests.exceptions.ReadTimeout("x")
    )
    raise error


class MediaMoveTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.show = self.tv_medias[0].item
        self.target = Item.objects.create(
            media_id="81189",
            source=Sources.TVDB.value,
            media_type=MediaTypes.TV.value,
            title="Moved Show",
        )

    def _move(self, payload=None, media_type="tv"):
        return self.call_api(
            "post",
            "api_media_move",
            args=(media_type, self.show.source, self.show.media_id),
            payload=payload
            or {
                "target_media_type": "tv",
                "target_source": "tvdb",
                "target_media_id": "81189",
            },
            headers=self.auth_headers,
        )

    def test_move_returns_the_new_identity(self):
        with patch(MIGRATE, return_value=self.target) as migrate:
            response = self._move()

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(),
            {"media_type": "tv", "source": "tvdb", "media_id": "81189", "title": "Moved Show"},
        )
        args = migrate.call_args.args
        self.assertEqual(args[0], self.user1)
        self.assertEqual(args[1], self.show)
        self.assertEqual(args[2:], ("tv", "tvdb", "81189"))

    def test_refused_move_is_400_with_the_reason(self):
        error = library_migration.LibraryMigrationError("Choose a destination title.")
        with patch(MIGRATE, side_effect=error):
            response = self._move()
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(response.json()["detail"], "Choose a destination title.")

    def test_provider_outage_is_503(self):
        with patch(
            MIGRATE,
            side_effect=lambda *args: _raise_from_provider(
                "The destination title could not be loaded."
            ),
        ):
            response = self._move()
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")

    def test_busy_database_is_503_database_busy(self):
        with patch(
            "api.fork_views_moves.run_retryable_db_operation",
            side_effect=OperationalError("database is locked"),
        ):
            response = self._move()
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "database_busy")
        self.assertEqual(response["Retry-After"], "5")

    def test_unknown_show_and_wrong_type(self):
        missing = self.call_api(
            "post",
            "api_media_move",
            args=("tv", "tmdb", "999999"),
            payload={},
            headers=self.auth_headers,
        )
        self.assertEqual(missing.status_code, HTTP.NOT_FOUND)
        self.assertEqual(self._move(media_type="movie").status_code, HTTP.BAD_REQUEST)


class AnimeGroupedMigrationTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.anime = Item.objects.create(
            media_id="5114",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Flat Anime",
        )
        self.grouped = Item.objects.create(
            media_id="31911",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            library_media_type=MediaTypes.ANIME.value,
            title="Grouped Anime",
        )

    def _migrate(self, provider="tmdb", media_id="5114"):
        return self.call_api(
            "post",
            "api_anime_migrate_grouped",
            args=(media_id,),
            payload={"provider": provider},
            headers=self.auth_headers,
        )

    def test_migrates_into_the_grouped_show(self):
        result = SimpleNamespace(grouped_tv=SimpleNamespace(item=self.grouped))
        with patch(
            "app.services.anime_migration.migrate_flat_anime_to_grouped",
            return_value=result,
        ) as migrate:
            response = self._migrate()

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["media_type"], "anime")
        self.assertEqual(response.json()["media_id"], "31911")
        migrate.assert_called_once_with(self.user1, self.anime, "tmdb")

    def test_refusal_is_400(self):
        with patch(
            "app.services.anime_migration.migrate_flat_anime_to_grouped",
            side_effect=anime_migration.AnimeMigrationError(
                "No TMDB mapping was found for this anime."
            ),
        ):
            response = self._migrate()
        self.assertEqual(response.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(
            response.json()["detail"], "No TMDB mapping was found for this anime."
        )

    def test_bad_provider_and_unknown_anime(self):
        self.assertEqual(self._migrate(provider="mal").status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self._migrate(media_id="1").status_code, HTTP.NOT_FOUND)
