"""Rebuilding an album's tracklist must keep every user's plays linked."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import Album, Artist, Item, MediaTypes, Music, Sources, Status, Track
from app.services.music import resync_album, sync_album_release_tracks

GET_RELEASE = "app.providers.musicbrainz.get_release"
GET_RELEASE_FOR_GROUP = "app.providers.musicbrainz.get_release_for_group"


def _release(tracks, release_group_id="group-1"):
    """Release data as `musicbrainz.get_release` returns it."""
    return {
        "release_group_id": release_group_id,
        "genres": [],
        "tracks": [
            {
                "disc_number": 1,
                "track_number": number,
                "title": title,
                "recording_id": recording_id,
                "duration_ms": 1000,
            }
            for number, (recording_id, title) in enumerate(tracks, start=1)
        ],
    }


class AlbumTracklistRebuildTests(TestCase):
    """An album with tracks A, B, C, each played by two users."""

    def setUp(self):
        user_model = get_user_model()
        self.users = [
            user_model.objects.create_user(username="alice", password="x"),
            user_model.objects.create_user(username="bob", password="x"),
        ]
        self.artist = Artist.objects.create(name="Artist")
        self.album = Album.objects.create(
            title="Album",
            artist=self.artist,
            musicbrainz_release_id="release-1",
            musicbrainz_release_group_id="group-1",
            tracks_populated=True,
        )
        self.tracks = {}
        self.plays = {}
        for number, recording_id in enumerate(("rec-a", "rec-b", "rec-c"), start=1):
            track = Track.objects.create(
                album=self.album,
                disc_number=1,
                track_number=number,
                title=recording_id,
                musicbrainz_recording_id=recording_id,
            )
            self.tracks[recording_id] = track
            item = Item.objects.create(
                media_id=recording_id,
                source=Sources.MUSICBRAINZ.value,
                media_type=MediaTypes.MUSIC.value,
                title=recording_id,
            )
            for user in self.users:
                self.plays[(user.username, recording_id)] = Music.objects.create(
                    user=user,
                    item=item,
                    artist=self.artist,
                    album=self.album,
                    track=track,
                    status=Status.IN_PROGRESS.value,
                )

    def _track_of(self, user, recording_id):
        play = self.plays[(user.username, recording_id)]
        play.refresh_from_db()
        return play.track_id

    def _assert_linked(self, recording_id):
        track = Track.objects.get(album=self.album, musicbrainz_recording_id=recording_id)
        for user in self.users:
            self.assertEqual(self._track_of(user, recording_id), track.id)

    @patch(GET_RELEASE)
    def test_same_tracklist_keeps_rows_and_links(self, get_release):
        get_release.return_value = _release(
            [("rec-a", "A"), ("rec-b", "B"), ("rec-c", "C")]
        )

        self.assertEqual(sync_album_release_tracks(self.album, "release-1"), 3)

        for recording_id, track in self.tracks.items():
            for user in self.users:
                self.assertEqual(self._track_of(user, recording_id), track.id)

    @patch(GET_RELEASE)
    def test_reordered_release_moves_tracks_and_keeps_each_play_on_its_song(
        self, get_release
    ):
        # Swapped positions would collide on the per-disc unique constraint.
        get_release.return_value = _release(
            [("rec-c", "C"), ("rec-b", "B"), ("rec-a", "A")]
        )

        sync_album_release_tracks(self.album, "release-2")

        positions = dict(
            Track.objects.filter(album=self.album).values_list(
                "musicbrainz_recording_id", "track_number"
            )
        )
        self.assertEqual(positions, {"rec-c": 1, "rec-b": 2, "rec-a": 3})
        for recording_id, track in self.tracks.items():
            for user in self.users:
                self.assertEqual(self._track_of(user, recording_id), track.id)

    @patch(GET_RELEASE)
    def test_dropped_recording_is_the_only_play_unlinked(self, get_release):
        get_release.return_value = _release(
            [("rec-a", "A"), ("rec-c", "C"), ("rec-d", "D")]
        )

        self.assertEqual(sync_album_release_tracks(self.album, "release-2"), 3)

        self._assert_linked("rec-a")
        self._assert_linked("rec-c")
        for user in self.users:
            self.assertIsNone(self._track_of(user, "rec-b"))
        self.assertTrue(
            Track.objects.filter(
                album=self.album, musicbrainz_recording_id="rec-d", track_number=3
            ).exists()
        )

    @patch(GET_RELEASE)
    def test_plays_unlinked_earlier_are_relinked(self, get_release):
        Music.objects.filter(item__media_id="rec-b").update(track=None)
        get_release.return_value = _release(
            [("rec-a", "A"), ("rec-b", "B"), ("rec-c", "C")]
        )

        sync_album_release_tracks(self.album, "release-1")

        self._assert_linked("rec-b")

    @patch(GET_RELEASE)
    @patch(GET_RELEASE_FOR_GROUP, return_value="release-2")
    def test_resync_keeps_links_and_uses_the_group_release(
        self, _for_group, get_release
    ):
        get_release.return_value = _release(
            [("rec-b", "B"), ("rec-a", "A"), ("rec-c", "C")]
        )

        result = resync_album(self.album)

        self.assertEqual(result.album, self.album)
        self.assertFalse(result.merged)
        self.assertEqual(result.track_count, 3)
        get_release.assert_called_once_with("release-2")
        self.album.refresh_from_db()
        self.assertEqual(self.album.musicbrainz_release_id, "release-2")
        for recording_id, track in self.tracks.items():
            for user in self.users:
                self.assertEqual(self._track_of(user, recording_id), track.id)

    @patch(GET_RELEASE)
    @patch(GET_RELEASE_FOR_GROUP, return_value=None)
    def test_resync_keeps_the_stored_release_when_the_group_finds_none(
        self, _for_group, get_release
    ):
        get_release.return_value = _release(
            [("rec-a", "A"), ("rec-b", "B"), ("rec-c", "C")]
        )

        result = resync_album(self.album)

        get_release.assert_called_once_with("release-1")
        self.assertEqual(result.track_count, 3)

    @patch(GET_RELEASE)
    def test_merging_a_duplicate_links_plays_to_the_canonical_tracks(
        self, get_release
    ):
        canonical = Album.objects.create(
            title="Album",
            artist=self.artist,
            musicbrainz_release_id="release-1",
            musicbrainz_release_group_id="group-canonical",
            tracks_populated=True,
        )
        canonical_tracks = {
            recording_id: Track.objects.create(
                album=canonical,
                disc_number=1,
                track_number=number,
                title=recording_id,
                musicbrainz_recording_id=recording_id,
            )
            for number, recording_id in enumerate(("rec-a", "rec-b", "rec-c"), start=1)
        }
        self.album.musicbrainz_release_group_id = ""
        self.album.save(update_fields=["musicbrainz_release_group_id"])
        get_release.return_value = _release(
            [("rec-a", "A"), ("rec-b", "B"), ("rec-c", "C")],
            release_group_id="group-canonical",
        )

        result = resync_album(self.album)

        self.assertTrue(result.merged)
        self.assertEqual(result.album, canonical)
        self.assertFalse(Album.objects.filter(pk=self.album.pk).exists())
        for (_username, recording_id), play in self.plays.items():
            play.refresh_from_db()
            self.assertEqual(play.album_id, canonical.id)
            self.assertEqual(play.track_id, canonical_tracks[recording_id].id)
