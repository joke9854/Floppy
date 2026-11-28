"""The web detail page API for anime (v2 P4-L3a) against the Django anime page.

Grouped anime (TMDB, TVDB) reads like a show in the anime bucket; flat MAL
anime lists its mapped episodes read-only. Provider calls are patched.
"""

import copy
from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

import events.tasks  # signal handlers reach events.tasks lazily
from app.models import (
    TV,
    Episode,
    Item,
    MediaTypes,
    Season,
    Sources,
    Status,
)
from app.services.metadata_resolution import MetadataResolutionResult
from integrations.models import IntegrationToken
from users.models import ThemeChoices


def _show(source, media_type, media_id="7001"):
    return {
        "media_id": media_id,
        "title": "Anime Show",
        "media_type": media_type,
        "source": source,
        "image": "https://image.tmdb.org/t/p/w500/anime.jpg",
        "synopsis": "A mage looks back.",
        "max_progress": 2,
        "details": {
            "seasons": 1,
            "episodes": 2,
            "first_air_date": "2023-09-29",
            "studios": ["Madhouse"],
        },
        "related": {
            "seasons": [
                {
                    "media_id": media_id,
                    "source": source,
                    "media_type": MediaTypes.SEASON.value,
                    "title": "Anime Show",
                    "season_number": 1,
                    "season_title": "Season 1",
                    "image": "https://image.tmdb.org/t/p/w500/s1.jpg",
                    "episode_count": 2,
                    "max_progress": 2,
                }
            ],
        },
    }


def _season(source, media_id="7001"):
    return {
        "media_id": media_id,
        "source": source,
        "media_type": MediaTypes.SEASON.value,
        "title": "Anime Show",
        "season_number": 1,
        "season_title": "Season 1",
        "max_progress": 2,
        "details": {"episodes": 2},
        "episodes": [
            {
                "episode_number": number,
                "air_date": f"2023-10-0{number}",
                "image": f"https://image.tmdb.org/t/p/w500/e{number}.jpg",
                "name": f"Episode 1x{number}",
                "overview": f"Overview {number}.",
                "runtime": 24,
            }
            for number in (1, 2)
        ],
    }


def _metadata_for(source, media_type, media_id="7001"):
    def metadata(requested, _media_id, _source, season_numbers=None, *_a, **_k):
        if requested == "tv_with_seasons":
            payload = _show(source, media_type, media_id)
            for number in season_numbers or []:
                payload[f"season/{number}"] = _season(source, media_id)
            return payload
        if requested == MediaTypes.SEASON.value:
            return _season(source, media_id)
        return copy.deepcopy(_show(source, media_type, media_id))

    return metadata


def _grouped_result(source, media_id="7001"):
    metadata = _show(source, MediaTypes.ANIME.value, media_id)
    metadata["identity_media_type"] = MediaTypes.TV.value
    metadata["library_media_type"] = MediaTypes.ANIME.value
    return MetadataResolutionResult(
        display_provider=source,
        identity_provider=source,
        mapping_status="identity",
        header_metadata=metadata,
        grouped_preview=None,
        provider_media_id=media_id,
    )


class _Base(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="anime-detail", password="x"
        )
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self.client.force_login(self.user)

    def _api(self, name, *args, **query):
        response = self.client.get(reverse(name, args=args), query)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def _tracked_show(self, source, library_media_type):
        item = Item.objects.create(
            media_id="7001",
            source=source,
            media_type=MediaTypes.TV.value,
            library_media_type=library_media_type,
            title="Anime Show",
            image="https://image.tmdb.org/t/p/w500/anime.jpg",
        )
        return TV.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )


class GroupedAnimeDetailTests(_Base):
    """TMDB grouped anime: the show machinery, in the anime bucket."""

    def _patches(self, source):
        return (
            patch(
                "app.providers.services.get_media_metadata",
                side_effect=_metadata_for(source, MediaTypes.ANIME.value),
            ),
            patch(
                "app.views.metadata_resolution.resolve_detail_metadata",
                return_value=_grouped_result(source),
            ),
        )

    def test_unwatched_episode_row_checks_into_the_anime_bucket(self):
        meta, resolve = self._patches(Sources.TMDB.value)
        with meta, resolve:
            shell = self._api("api_detail_shell", "anime", "tmdb", "7001")
            sections = self._api("api_detail_sections", "anime", "tmdb", "7001")

        self.assertEqual(shell["media_type"], "anime")
        self.assertEqual(shell["meta"]["seasons"], 1)
        self.assertEqual(
            [cover["short"] for cover in sections["seasons"]], ["S1"]
        )
        self.assertIn(
            {"label": "Network", "value": "Madhouse"}, sections["info"]
        )
        rows = sections["season"]["episodes"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["check"]["library_media_type"], "anime")
            self.assertEqual(row["check"]["source"], "tmdb")
        self.assertEqual(
            rows[0]["url"],
            "/details/tmdb/anime/7001/anime-show/season/1/episode/1",
        )

    def test_hero_mark_next_carries_the_anime_bucket(self):
        self._tracked_show(Sources.TMDB.value, MediaTypes.ANIME.value)
        meta, resolve = self._patches(Sources.TMDB.value)
        with meta, resolve:
            shell = self._api("api_detail_shell", "anime", "tmdb", "7001")

        action = shell["action"]
        if action and action["episode"]:
            self.assertEqual(action["episode"]["library_media_type"], "anime")
        else:
            self.assertEqual(action["kind"], "episode")

    def test_season_endpoint_reads_the_anime_bucket(self):
        tv = self._tracked_show(Sources.TMDB.value, MediaTypes.ANIME.value)
        season_item = Item.objects.create(
            media_id="7001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            library_media_type=MediaTypes.ANIME.value,
            season_number=1,
            title="Anime Show",
            image="https://image.tmdb.org/t/p/w500/anime.jpg",
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
        )
        episode_item = Item.objects.create(
            media_id="7001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            library_media_type=MediaTypes.ANIME.value,
            season_number=1,
            episode_number=1,
            title="Anime Show",
            image="https://image.tmdb.org/t/p/w500/anime.jpg",
        )
        Episode.objects.create(
            item=episode_item,
            related_season=season,
            end_date=datetime(2024, 1, 3, 21, 13, tzinfo=UTC),
        )
        meta, resolve = self._patches(Sources.TMDB.value)
        with meta, resolve:
            anime = self._api("api_detail_season_anime", "tmdb", "7001", season=1)
            tv_season = self._api("api_detail_season", "tmdb", "7001", season=1)

        self.assertTrue(anime["episodes"][0]["watched"])
        self.assertEqual(anime["episodes"][0]["check"]["library_media_type"], "anime")
        self.assertIn("/anime/7001/", anime["episodes"][0]["url"])
        self.assertIn("/tv/7001/", tv_season["episodes"][0]["url"])

    def test_check_target_ensures_into_the_anime_bucket_exactly(self):
        meta, resolve = self._patches(Sources.TMDB.value)
        with meta, resolve:
            sections = self._api("api_detail_sections", "anime", "tmdb", "7001")
        target = sections["season"]["episodes"][0]["check"]
        _, raw = IntegrationToken.generate(
            user=self.user, name="anime-check", scopes=["*"]
        )
        watched_at = "2024-01-03T21:13:07.123456Z"
        payload = {
            "events": [
                {
                    "season_number": target["season_number"],
                    "episode_number": target["episode_number"],
                    "watched_at": watched_at,
                    "client_event_id": "d5ac6fbf-8103-4cfe-9693-fb33e363a121",
                }
            ],
            "library_media_type": target["library_media_type"],
        }

        def post():
            return self.client.post(
                reverse(
                    "api_media_episode_ensure",
                    args=("tv", target["source"], target["media_id"]),
                ),
                payload,
                content_type="application/json",
                HTTP_X_API_KEY=raw,
            )

        with patch(
            "app.providers.services.get_media_metadata",
            side_effect=_metadata_for(Sources.TMDB.value, MediaTypes.ANIME.value),
        ):
            first = post()
            second = post()

        self.assertEqual(first.status_code, 200, first.content[:300])
        self.assertEqual(first.json()["results"][0]["status"], "created")
        self.assertEqual(second.json()["results"][0]["status"], "already_satisfied")
        episodes = Episode.objects.filter(item__media_id="7001")
        self.assertEqual(episodes.count(), 1)
        episode = episodes.get()
        self.assertEqual(episode.item.library_media_type, "anime")
        self.assertEqual(
            episode.end_date, datetime(2024, 1, 3, 21, 13, 7, 123456, tzinfo=UTC)
        )
        self.assertEqual(
            TV.objects.filter(item__media_id="7001").exclude(
                item__library_media_type="anime"
            ).count(),
            0,
        )
        self.assertEqual(TV.objects.filter(item__media_id="7001").count(), 1)


class CheckableSourceTests(_Base):
    """A check target only exists for a source the ensure endpoint accepts."""

    def test_the_rule_is_the_ensure_endpoints(self):
        from api.details_screen import _can_check
        from api.helpers import check_source_type

        # Runtime VALID_SOURCES: the fork adds tvdb to tv (api/fork_helpers.py).
        for source in ("tmdb", "tvdb", "manual", "mal", "igdb"):
            self.assertEqual(_can_check(source), check_source_type("tv", source))
        self.assertFalse(_can_check("mal"))
        self.assertTrue(_can_check("tmdb"))

    def test_tvdb_anime_rows_check_into_the_anime_bucket(self):
        self._tracked_show(Sources.TVDB.value, MediaTypes.ANIME.value)
        with (
            patch(
                "app.providers.services.get_media_metadata",
                side_effect=_metadata_for(Sources.TVDB.value, MediaTypes.ANIME.value),
            ),
            patch(
                "app.views.metadata_resolution.resolve_detail_metadata",
                return_value=_grouped_result(Sources.TVDB.value),
            ),
        ):
            sections = self._api("api_detail_sections", "anime", "tvdb", "7001")

        rows = sections["season"]["episodes"]
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["check"]["source"], "tvdb")
            self.assertEqual(row["check"]["library_media_type"], "anime")

    def test_an_unchecked_source_has_no_check_and_no_mark_next(self):
        from api import details_screen

        with patch.object(details_screen, "_can_check", return_value=False):
            self._tracked_show(Sources.TMDB.value, MediaTypes.ANIME.value)
            meta = patch(
                "app.providers.services.get_media_metadata",
                side_effect=_metadata_for(Sources.TMDB.value, MediaTypes.ANIME.value),
            )
            resolve = patch(
                "app.views.metadata_resolution.resolve_detail_metadata",
                return_value=_grouped_result(Sources.TMDB.value),
            )
            with meta, resolve:
                shell = self._api("api_detail_shell", "anime", "tmdb", "7001")
                sections = self._api("api_detail_sections", "anime", "tmdb", "7001")

        self.assertIsNone(shell["action"])
        rows = sections["season"]["episodes"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["check"] is None for row in rows))


@override_settings(TVDB_API_KEY="test-tvdb-key")
class FlatAnimeDetailTests(_Base):
    """Flat MAL anime: the mapped episode preview, read-only."""

    def test_mapped_preview_rows_link_to_the_provider_page_without_checks(self):
        base = {
            "media_id": "52991",
            "title": "Frieren",
            "media_type": MediaTypes.ANIME.value,
            "source": Sources.MAL.value,
            "source_url": "https://myanimelist.net/anime/52991",
            "max_progress": 2,
            "image": "https://example.com/frieren.jpg",
            "synopsis": "A mage looks back.",
            "details": {"episodes": 2},
            "related": {},
            "cast": [],
            "crew": [],
            "studios_full": [],
        }
        grouped = {
            "media_id": "9350138",
            "source": Sources.TVDB.value,
            "media_type": MediaTypes.TV.value,
            "title": "Frieren",
            "related": {"seasons": [{"season_number": 1, "episode_count": 2}]},
            "season/1": {
                "media_id": "9350138",
                "source": Sources.TVDB.value,
                "media_type": MediaTypes.SEASON.value,
                "season_number": 1,
                "season_title": "Season 1",
                "details": {"episodes": 2},
                "episodes": [
                    {
                        "episode_number": number,
                        "air_date": f"2023-09-2{number}",
                        "image": f"https://example.com/ep{number}.jpg",
                        "name": f"Mapped {number}",
                        "overview": "",
                        "runtime": 24,
                    }
                    for number in (1, 2)
                ],
            },
        }

        def metadata(requested, *_args, **_kwargs):
            return grouped if requested == "tv_with_seasons" else base

        Item.objects.create(
            media_id="52991",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Frieren",
            image="https://example.com/frieren.jpg",
        )
        with (
            patch("app.providers.services.get_media_metadata", side_effect=metadata),
            patch(
                "app.views.metadata_resolution.resolve_detail_metadata",
                return_value=MetadataResolutionResult(
                    display_provider=Sources.MAL.value,
                    identity_provider=Sources.MAL.value,
                    mapping_status="identity",
                    header_metadata=copy.deepcopy(base),
                    grouped_preview=None,
                    provider_media_id="52991",
                    grouped_preview_target=None,
                ),
            ),
        ):
            shell = self._api("api_detail_shell", "anime", "mal", "52991")
            sections = self._api("api_detail_sections", "anime", "mal", "52991")

        self.assertIsNone(shell["action"])
        rows = sections["flat_episodes"]
        self.assertEqual([row["title"] for row in rows], ["Mapped 1", "Mapped 2"])
        self.assertTrue(all(row["check"] is None for row in rows))
        self.assertEqual(
            rows[0]["url"],
            "/details/tvdb/anime/9350138/frieren/season/1/episode/1",
        )
        self.assertEqual(sections["seasons"], [])
        self.assertIsNone(sections["season"])


class AnimeEpisodeScreenTests(_Base):
    """GET details/episode/... with ?parent=anime."""

    def _api_episode(self, **query):
        with (
            patch("app.views.tmdb.episode", return_value={}),
            patch(
                "app.providers.services.get_media_metadata",
                side_effect=_metadata_for(Sources.TMDB.value, MediaTypes.TV.value),
            ),
            patch(
                "app.providers.tmdb.process_episodes",
                return_value=[
                    {
                        "media_id": "7001",
                        "source": Sources.TMDB.value,
                        "media_type": MediaTypes.EPISODE.value,
                        "season_number": 1,
                        "episode_number": number,
                        "title": f"Episode {number}",
                        "air_date": f"2023-01-{number:02d}",
                        "overview": "",
                    }
                    for number in (1, 2)
                ],
            ),
        ):
            return self.client.get(
                reverse("api_episode_screen", args=["tmdb", "7001", 1, 1]), query
            )

    def test_parent_anime_uses_the_anime_bucket_and_urls(self):
        body = self._api_episode(parent="anime").json()

        self.assertEqual(body["check"]["library_media_type"], "anime")
        self.assertIn("/anime/7001/", body["show_url"])
        self.assertIn("/anime/7001/", body["next_url"])

    def test_without_parent_nothing_changes(self):
        body = self._api_episode().json()

        self.assertIn("/tv/7001/", body["show_url"])
        self.assertIn("/tv/7001/", body["next_url"])
        self.assertNotEqual(body["check"]["library_media_type"], "anime")
