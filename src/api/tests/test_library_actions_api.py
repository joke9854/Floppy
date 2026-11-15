"""FORK (P1-D): preferences and bulk actions the web had and the API lacked."""

from http import HTTPStatus as HTTP  # noqa: N814
from types import SimpleNamespace
from unittest.mock import patch

import requests

from app.models import (
    Album,
    Artist,
    CollectionEntry,
    CollectionField,
    CollectionFieldGroup,
    HardcoverEditionPreference,
    Item,
    ItemTag,
    MediaTypes,
    MetadataProviderPreference,
    MusicReleasePreference,
    Sources,
    Tag,
)
from app.providers import services

from .base import FloppyApiTestCase

LANGUAGES = [("", "Server Default (en-US)"), ("it", "Italian"), ("ja", "Japanese")]


def _outage():
    return services.ProviderAPIError("tmdb", requests.exceptions.ReadTimeout("x"))


class ProviderPreferencePatchTests(FloppyApiTestCase):
    """PATCH provider-preference sets the language or remaps the title."""

    def setUp(self):
        super().setUp()
        self.item = self.movie_medias[0].item

    def _patch(self, payload):
        return self.call_api(
            "patch",
            "api_media_provider_preference",
            args=("movie", self.item.source, self.item.media_id),
            payload=payload,
            headers=self.auth_headers,
        )

    @patch("app.providers.tmdb.metadata_languages", return_value=LANGUAGES)
    def test_language_is_saved_and_read_back(self, _languages):
        response = self._patch({"language": "it"})

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["language"], "it")
        read = self.call_api(
            "get",
            "api_media_provider_preference",
            args=("movie", self.item.source, self.item.media_id),
            headers=self.auth_headers,
        )
        self.assertEqual(read.json()["language"], "it")

    @patch("app.providers.tmdb.metadata_languages", return_value=LANGUAGES)
    def test_empty_language_resets_to_server_default(self, _languages):
        MetadataProviderPreference.objects.create(
            user=self.user1, item=self.item, language="ja"
        )
        response = self._patch({"language": ""})
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            MetadataProviderPreference.objects.get(user=self.user1, item=self.item).language,
            "",
        )

    @patch("app.providers.tmdb.metadata_languages", return_value=LANGUAGES)
    def test_unknown_language_is_400(self, _languages):
        self.assertEqual(self._patch({"language": "xx"}).status_code, HTTP.BAD_REQUEST)

    @patch("app.providers.tmdb.metadata_languages", side_effect=_outage())
    def test_language_check_during_outage_is_503(self, _languages):
        response = self._patch({"language": "it"})
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")

    def test_remap_needs_a_different_provider_and_an_id(self):
        same = self._patch({"provider": self.item.source, "provider_media_id": "1"})
        self.assertEqual(same.status_code, HTTP.BAD_REQUEST)
        empty = self._patch({"provider": "tvdb", "provider_media_id": ""})
        self.assertEqual(empty.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(self._patch({}).status_code, HTTP.BAD_REQUEST)

    @patch("app.library_actions.metadata_resolution.upsert_provider_links")
    @patch(
        "api.fork_views_metadata.metadata_resolution.available_metadata_provider_options",
        return_value=[SimpleNamespace(value="tmdb"), SimpleNamespace(value="tvdb")],
    )
    def test_remap_links_and_prefers_the_provider(self, _options, upsert):
        response = self._patch({"provider": "tvdb", "provider_media_id": "81189"})

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["provider"], "tvdb")
        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[1], {"media_id": "81189"})
        self.assertEqual(upsert.call_args.kwargs["provider"], "tvdb")


class MetadataLanguagesTests(FloppyApiTestCase):
    @patch("app.providers.tmdb.metadata_languages", return_value=LANGUAGES)
    def test_lists_codes(self, _languages):
        response = self.call_api("get", "api_metadata_languages", headers=self.auth_headers)
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()[1], {"code": "it", "name": "Italian"})


class HardcoverEditionTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.book = Item.objects.create(
            media_id="4242",
            source=Sources.HARDCOVER.value,
            media_type=MediaTypes.BOOK.value,
            title="A Book",
        )

    @patch(
        "app.providers.hardcover.editions",
        return_value=[{"id": "9", "title": "Paperback", "format": "Paperback"}],
    )
    def test_list_and_pick_an_edition(self, _editions):
        listed = self.call_api(
            "get", "api_hardcover_edition", args=("4242",), headers=self.auth_headers
        )
        self.assertEqual(listed.status_code, HTTP.OK)
        self.assertIsNone(listed.json()["edition_id"])
        self.assertEqual(listed.json()["editions"][0]["id"], "9")
        self.assertIsNone(listed.json()["editions"][0]["publisher"])

        picked = self.call_api(
            "put",
            "api_hardcover_edition",
            args=("4242",),
            payload={"edition_id": "9"},
            headers=self.auth_headers,
        )
        self.assertEqual(picked.status_code, HTTP.OK)
        self.assertEqual(
            HardcoverEditionPreference.objects.get(user=self.user1, item=self.book).edition_id,
            "9",
        )

    def test_unknown_book_is_404_and_missing_edition_is_400(self):
        missing = self.call_api(
            "put",
            "api_hardcover_edition",
            args=("1",),
            payload={"edition_id": "9"},
            headers=self.auth_headers,
        )
        self.assertEqual(missing.status_code, HTTP.NOT_FOUND)
        empty = self.call_api(
            "put",
            "api_hardcover_edition",
            args=("4242",),
            payload={},
            headers=self.auth_headers,
        )
        self.assertEqual(empty.status_code, HTTP.BAD_REQUEST)


class MusicReleaseTests(FloppyApiTestCase):
    RELEASES = [
        {"release_id": "rel-1", "title": "Album", "formats": ["CD"], "track_count": 10},
    ]

    def setUp(self):
        super().setUp()
        artist = Artist.objects.create(name="Band")
        self.album = Album.objects.create(
            title="Album", artist=artist, musicbrainz_release_group_id="group-1"
        )

    def _put(self, release_id):
        return self.call_api(
            "put",
            "api_music_album_release",
            args=(self.album.id,),
            payload={"release_id": release_id},
            headers=self.auth_headers,
        )

    @patch("api.fork_views_library.sync_album_release_tracks", return_value=10)
    @patch("app.providers.musicbrainz.get_release_group_releases", return_value=RELEASES)
    def test_pick_a_release_rebuilds_tracks(self, _releases, sync):
        response = self._put("rel-1")

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(),
            {"release_id": "rel-1", "tracks_synced": True, "track_count": 10},
        )
        sync.assert_called_once_with(self.album, "rel-1")
        self.assertTrue(
            MusicReleasePreference.objects.filter(
                user=self.user1, album=self.album, release_id="rel-1"
            ).exists()
        )

    @patch("app.providers.musicbrainz.get_release_group_releases", return_value=RELEASES)
    def test_release_of_another_album_is_400(self, _releases):
        self.assertEqual(self._put("rel-other").status_code, HTTP.BAD_REQUEST)

    @patch(
        "api.fork_views_library.sync_album_release_tracks",
        side_effect=RuntimeError("musicbrainz down"),
    )
    @patch("app.providers.musicbrainz.get_release_group_releases", return_value=RELEASES)
    def test_saved_even_when_the_tracklist_cannot_refresh(self, _releases, _sync):
        response = self._put("rel-1")
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertFalse(response.json()["tracks_synced"])

    @patch("app.providers.musicbrainz.get_release_group_releases", side_effect=_outage())
    def test_musicbrainz_outage_is_503(self, _releases):
        response = self._put("rel-1")
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)

    @patch("app.providers.musicbrainz.get_release_group_releases", return_value=RELEASES)
    def test_list_releases(self, _releases):
        response = self.call_api(
            "get", "api_music_album_release", args=(self.album.id,), headers=self.auth_headers
        )
        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(response.json()["releases"][0]["formats"], ["CD"])


class AlbumResyncTests(FloppyApiTestCase):
    """POST music/albums/{id}/resync/ (the service is covered in app tests)."""

    def setUp(self):
        super().setUp()
        artist = Artist.objects.create(name="Band")
        self.album = Album.objects.create(
            title="Album",
            artist=artist,
            musicbrainz_release_id="rel-1",
            musicbrainz_release_group_id="group-1",
        )

    def _post(self, album_id=None):
        return self.call_api(
            "post",
            "api_music_album_resync",
            args=(album_id or self.album.id,),
            headers=self.auth_headers,
        )

    @patch("app.providers.musicbrainz.get_release_for_group", return_value="rel-1")
    @patch(
        "app.providers.musicbrainz.get_release",
        return_value={
            "release_group_id": "group-1",
            "genres": [],
            "tracks": [
                {"disc_number": 1, "track_number": 1, "title": "One", "recording_id": "r1"},
            ],
        },
    )
    def test_resync_refreshes_the_tracklist(self, _release, _for_group):
        response = self._post()

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(),
            {"album_id": self.album.id, "merged": False, "track_count": 1},
        )

    @patch(
        "api.fork_views_library.resync_album",
        side_effect=lambda album: SimpleNamespace(
            album=SimpleNamespace(id=999), merged=True, track_count=None
        ),
    )
    def test_merge_returns_the_surviving_album(self, _resync):
        response = self._post()
        self.assertEqual(
            response.json(), {"album_id": 999, "merged": True, "track_count": None}
        )

    @patch("app.providers.musicbrainz.get_release_for_group", return_value=None)
    def test_no_release_is_400(self, _for_group):
        self.album.musicbrainz_release_id = ""
        self.album.save(update_fields=["musicbrainz_release_id"])
        self.assertEqual(self._post().status_code, HTTP.BAD_REQUEST)

    @patch("app.providers.musicbrainz.get_release_for_group", return_value="rel-1")
    @patch("app.providers.musicbrainz.get_release", side_effect=_outage())
    def test_musicbrainz_outage_is_503(self, _release, _for_group):
        response = self._post()
        self.assertEqual(response.status_code, HTTP.SERVICE_UNAVAILABLE)
        self.assertEqual(response.json()["code"], "provider_unavailable")

    def test_unknown_album_is_404(self):
        self.assertEqual(self._post(album_id=987654).status_code, HTTP.NOT_FOUND)


class TagItemsTests(FloppyApiTestCase):
    def setUp(self):
        super().setUp()
        self.tag = Tag.objects.create(user=self.user1, name="Favourites")
        self.ids = [media.item.id for media in self.movie_medias]

    def _post(self, payload, tag_id=None):
        return self.call_api(
            "post",
            "api_tag_items",
            args=(tag_id or self.tag.id,),
            payload=payload,
            headers=self.auth_headers,
        )

    def test_add_then_remove(self):
        added = self._post({"action": "add", "item_ids": [*self.ids, 99999999]})
        self.assertEqual(added.status_code, HTTP.OK)
        self.assertEqual(added.json()["item_ids"], sorted(self.ids))
        self.assertEqual(ItemTag.objects.filter(tag=self.tag).count(), len(self.ids))

        removed = self._post({"action": "remove", "item_ids": self.ids[:1]})
        self.assertEqual(removed.status_code, HTTP.OK)
        self.assertEqual(ItemTag.objects.filter(tag=self.tag).count(), len(self.ids) - 1)

    def test_someone_elses_tag_is_404(self):
        other = Tag.objects.create(user=self.user2, name="Theirs")
        response = self._post({"action": "add", "item_ids": self.ids}, tag_id=other.id)
        self.assertEqual(response.status_code, HTTP.NOT_FOUND)

    def test_bad_payloads_are_400(self):
        for payload in (
            {"action": "toggle", "item_ids": self.ids},
            {"action": "add", "item_ids": []},
            {"action": "add", "item_ids": ["x"]},
            {"action": "add", "item_ids": list(range(1, 502))},
        ):
            with self.subTest(payload=str(payload)[:40]):
                self.assertEqual(self._post(payload).status_code, HTTP.BAD_REQUEST)


class CollectionBulkTests(FloppyApiTestCase):
    def test_adds_new_items_and_reports_the_rest(self):
        first, second = (media.item for media in self.movie_medias[:2])
        CollectionEntry.objects.create(user=self.user1, item=first)

        response = self.call_api(
            "post",
            "api_collection_bulk",
            payload={"item_ids": [first.id, second.id, 99999999]},
            headers=self.auth_headers,
        )

        self.assertEqual(response.status_code, HTTP.OK)
        self.assertEqual(
            response.json(),
            {"created": 1, "already_present": 1, "skipped_ids": [99999999]},
        )
        self.assertTrue(
            CollectionEntry.objects.filter(user=self.user1, item=second).exists()
        )


class CollectionFieldsTests(FloppyApiTestCase):
    def _put(self, payload):
        return self.call_api(
            "put", "api_collection_fields", payload=payload, headers=self.auth_headers
        )

    def test_create_read_and_delete_by_omission(self):
        created = self._put(
            {
                "groups": [
                    {
                        "name": "Physical",
                        "fields": [
                            {
                                "label": "Format",
                                "field_type": "select",
                                "options": ["Blu-ray", "DVD"],
                                "media_types": ["movie"],
                            },
                            {
                                "label": "Shelf",
                                "field_type": "text",
                                "media_types": ["movie"],
                            },
                        ],
                    }
                ]
            }
        )
        self.assertEqual(created.status_code, HTTP.OK)
        group = created.json()["groups"][0]
        self.assertEqual([field["label"] for field in group["fields"]], ["Format", "Shelf"])

        read = self.call_api("get", "api_collection_fields", headers=self.auth_headers)
        self.assertEqual(read.json(), created.json())

        kept = group["fields"][0]
        trimmed = self._put(
            {"groups": [{"id": group["id"], "name": "Physical", "fields": [kept]}]}
        )
        self.assertEqual(trimmed.status_code, HTTP.OK)
        self.assertEqual(CollectionField.objects.filter(group__user=self.user1).count(), 1)

    def test_invalid_schema_is_400_and_foreign_ids_are_404(self):
        invalid = self._put({"groups": [{"name": "", "fields": []}]})
        self.assertEqual(invalid.status_code, HTTP.BAD_REQUEST)
        self.assertEqual(invalid.json()["detail"], "Group name is required")

        theirs = CollectionFieldGroup.objects.create(user=self.user2, name="Theirs")
        foreign = self._put({"groups": [{"id": theirs.id, "name": "Mine", "fields": []}]})
        self.assertEqual(foreign.status_code, HTTP.NOT_FOUND)
