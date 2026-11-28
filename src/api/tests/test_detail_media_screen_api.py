"""The web music and podcast detail pages (v2 P4-L2) against the Django pages.

Every provider and network call the pages' builders make is patched, so the
tests run offline.
"""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app import fork_services_music, fork_services_podcast
from app.models import (
    Album,
    AlbumTracker,
    Artist,
    ArtistTracker,
    Music,
    Podcast,
    PodcastEpisode,
    PodcastShow,
    Status,
    Track,
)
from users.models import ThemeChoices

MBID = "11111111-1111-1111-1111-111111111111"
FIRST = datetime(2026, 3, 1, 21, 15, 30, tzinfo=UTC)
SECOND = datetime(2026, 3, 9, 8, 5, 0, tzinfo=UTC)


def _artist_patches():
    return (
        patch("app.services.music.sync_artist_discography", return_value=0),
        patch("app.services.music.sync_artist_members", return_value=0),
        patch(
            "app.providers.musicbrainz.get_artist",
            return_value={
                "type": "Group",
                "country": "GB",
                "area": "London",
                "begin_date": "1990",
                "end_date": "",
                "genres": [{"name": "shoegaze"}],
                "tags": [],
                "rating": 4.2,
                "rating_count": 12,
                "bio": "A band.",
            },
        ),
        patch("app.tasks.prefetch_artist_images_batch"),
    )


def _album_patches():
    return (
        patch("app.services.music.sync_artist_discography", return_value=0),
        patch("app.services.music.ensure_album_has_release_id"),
        patch("app.services.music.album_artist_credits_need_sync", return_value=False),
        patch("app.services.music.populate_album_implied_genres", return_value=False),
        patch("app.services.music.populate_album_tracks"),
        patch("app.services.music.sync_album_artist_credits"),
        patch("app.services.music_scrobble.is_incomplete_album", return_value=False),
        patch("app.providers.musicbrainz.get_release", return_value={}),
    )


class _Patched(TestCase):
    patches = ()

    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="media", password="x")
        self.user.theme = ThemeChoices.CINETRACK
        self.user.save(update_fields=["theme"])
        self.client.force_login(self.user)
        self.mocks = {}
        for active in self.patches():
            mock = active.start()
            self.addCleanup(active.stop)
            self.mocks[active.attribute] = mock


class MusicArtistScreenTests(_Patched):
    patches = staticmethod(_artist_patches)

    def setUp(self):
        super().setUp()
        self.artist = Artist.objects.create(
            name="Slowdive", musicbrainz_id=MBID, image=""
        )
        self.artist.discography_synced_at = datetime.now(UTC)
        self.artist.save()
        self.album = Album.objects.create(
            title="Souvlaki",
            artist=self.artist,
            musicbrainz_release_id="22222222-2222-2222-2222-222222222222",
            release_date=date(1993, 6, 1),
            release_type="Album",
        )
        AlbumTracker.objects.create(user=self.user, album=self.album, score=9)
        ArtistTracker.objects.create(
            user=self.user,
            artist=self.artist,
            status=Status.IN_PROGRESS.value,
            score=8.5,
        )

    def test_fields_and_discography(self):
        response = self.client.get(
            reverse("api_music_artist_screen", kwargs={"artist_id": self.artist.id})
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["artist"]["id"], self.artist.id)
        self.assertEqual(data["artist"]["name"], "Slowdive")
        self.assertEqual(data["artist"]["bio"], "A band.")
        self.assertTrue(
            data["artist"]["url"].startswith(f"/details/music/artist/{self.artist.id}/")
        )
        self.assertEqual(
            data["artist"]["musicbrainz_url"], f"https://musicbrainz.org/artist/{MBID}"
        )
        self.assertEqual(data["rating"], {"rating": 4.2, "rating_count": 12})
        self.assertEqual(
            data["tracker"], {"status": Status.IN_PROGRESS.value, "score": 8.5}
        )
        self.assertEqual(data["genres"], [{"name": "Shoegaze", "url": ""}])
        details = {row["label"]: row["value"] for row in data["details"]}
        self.assertEqual(details["Type"], "Group")
        self.assertEqual(details["Origin"], "London")
        self.assertEqual(details["Formed"], "1990")
        self.assertEqual(details["Releases"], "1")
        self.assertNotIn("Disbanded", details)
        self.assertEqual(len(data["discography"]), 1)
        group = data["discography"][0]
        self.assertEqual(group["label"], "Album")
        row = group["albums"][0]
        self.assertEqual(row["id"], self.album.id)
        self.assertEqual(row["title"], "Souvlaki")
        self.assertEqual(row["release_date"], "1993-06-01")
        self.assertEqual(row["score"], 9.0)
        self.assertEqual(row["play_count"], 0)
        self.assertTrue(
            row["url"].startswith(f"/details/music/artist/{self.artist.id}/")
        )
        self.assertIn(f"/album/{self.album.id}/", row["url"])
        self.assertEqual(data["history_url"], f"/history?artist={self.artist.id}")
        self.assertEqual(
            data["sync_url"],
            f"/api/v1/music/artists/{self.artist.id}/sync-discography/",
        )

    def test_unknown_artist_is_404(self):
        response = self.client.get(
            reverse("api_music_artist_screen", kwargs={"artist_id": 9999})
        )
        self.assertEqual(response.status_code, 404)

    def test_redirect_is_400(self):
        from django.shortcuts import redirect

        with patch(
            "app.music_views.build_music_artist_context", return_value=redirect("/x/")
        ):
            response = self.client.get(
                reverse("api_music_artist_screen", kwargs={"artist_id": self.artist.id})
            )
        self.assertEqual(response.status_code, 400)


class MusicAlbumScreenTests(_Patched):
    patches = staticmethod(_album_patches)

    def setUp(self):
        super().setUp()
        self.artist = Artist.objects.create(name="Slowdive", musicbrainz_id=MBID)
        self.album = Album.objects.create(
            title="Souvlaki",
            artist=self.artist,
            musicbrainz_release_id="22222222-2222-2222-2222-222222222222",
            release_date=date(1993, 6, 1),
            release_type="Album",
            tracks_populated=True,
            genres=["Shoegaze"],
            implied_genres=["Rock", "shoegaze"],
        )
        self.track1 = Track.objects.create(
            album=self.album,
            title="Alison",
            track_number=1,
            musicbrainz_recording_id="33333333-3333-3333-3333-333333333333",
            duration_ms=233000,
        )
        self.track2 = Track.objects.create(
            album=self.album,
            title="Machine Gun",
            track_number=2,
            musicbrainz_recording_id="44444444-4444-4444-4444-444444444444",
            duration_ms=263000,
        )
        fork_services_music.record_song_play(
            self.user, self.album, track=self.track1, end_date=FIRST
        )
        # A later play: beyond the five minutes the page treats as one listen.
        fork_services_music.record_song_play(
            self.user, self.album, track=self.track1, end_date=SECOND
        )
        fork_services_music.record_song_play(
            self.user,
            self.album,
            track=self.track2,
            end_date=FIRST + timedelta(hours=1),
        )

    def _url(self, artist_id=None, album_id=None):
        return reverse(
            "api_music_album_screen",
            kwargs={
                "artist_id": artist_id or self.artist.id,
                "album_id": album_id or self.album.id,
            },
        )

    def test_tracks_with_exact_play_instants(self):
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertEqual(data["album"]["title"], "Souvlaki")
        self.assertEqual(data["album"]["artists"][0]["id"], self.artist.id)
        self.assertEqual(data["total_tracks"], 2)
        self.assertEqual(data["release_date"], "1993-06-01")
        self.assertIsNone(data["release"])
        self.assertEqual(
            data["genres"],
            [
                {"name": "Shoegaze", "url": "/medialist/music?genre=Shoegaze"},
                {"name": "Rock", "url": ""},
            ],
        )
        self.assertEqual(
            data["sync_url"], f"/api/v1/music/albums/{self.album.id}/resync/"
        )
        self.assertEqual(data["history_url"], f"/history?album={self.album.id}")
        first, second = data["tracks"]
        self.assertEqual(first["track_id"], self.track1.id)
        self.assertEqual(first["recording_id"], self.track1.musicbrainz_recording_id)
        self.assertEqual(first["title"], "Alison")
        self.assertEqual(first["number"], 1)
        self.assertEqual(first["duration"], "3:53")
        self.assertEqual(first["play_count"], 2)
        self.assertEqual(
            [play["end_date"] for play in first["plays"]],
            [
                SECOND.isoformat(),
                FIRST.isoformat(),
            ],
        )
        self.assertEqual(first["last_played"], SECOND.isoformat())
        history_ids = [play["history_id"] for play in first["plays"]]
        self.assertEqual(len(set(history_ids)), 2)
        self.assertEqual(second["play_count"], 1)
        self.assertEqual(
            second["plays"][0]["end_date"], (FIRST + timedelta(hours=1)).isoformat()
        )

    def test_history_id_is_what_the_delete_endpoint_removes(self):
        data = self.client.get(self._url()).json()
        play = data["tracks"][0]["plays"][0]
        response = self.client.delete(f"/api/v1/history/music/{play['history_id']}/")
        self.assertEqual(response.status_code, 204)
        again = self.client.get(self._url()).json()
        self.assertEqual(again["tracks"][0]["play_count"], 1)

    def _music(self, track):
        return Music.objects.get(user=self.user, album=self.album, track=track)

    def _delete_play(self, music, end_date):
        record = music.history.get(end_date=end_date)
        response = self.client.delete(f"/api/v1/history/music/{record.history_id}/")
        self.assertEqual(response.status_code, 204)

    def test_deleting_the_latest_play_moves_the_row_to_the_one_before(self):
        music = self._music(self.track1)
        self.assertEqual(music.end_date, SECOND)
        self._delete_play(music, SECOND)
        music.refresh_from_db()
        self.assertEqual(music.end_date, FIRST)
        # The move adds no play.
        self.assertEqual(music.history.filter(end_date__isnull=False).count(), 1)

    def test_deleting_an_older_play_keeps_the_row(self):
        music = self._music(self.track1)
        self._delete_play(music, FIRST)
        music.refresh_from_db()
        self.assertEqual(music.end_date, SECOND)

    def test_deleting_the_only_play_clears_the_row(self):
        music = self._music(self.track2)
        self._delete_play(music, FIRST + timedelta(hours=1))
        music.refresh_from_db()
        self.assertIsNone(music.end_date)

    def test_another_users_plays_are_not_shown(self):
        other = get_user_model().objects.create_user(username="other", password="x")
        fork_services_music.record_song_play(
            other, self.album, track=self.track2, end_date=SECOND
        )
        data = self.client.get(self._url()).json()
        self.assertEqual(data["tracks"][1]["play_count"], 1)

    def test_canonical_move_is_400(self):
        other = Album.objects.create(title="Souvlaki", artist=self.artist)
        with patch("app.services.music.canonicalize_album", return_value=other):
            response = self.client.get(self._url())
        self.assertEqual(response.status_code, 400)

    def test_artist_mismatch_is_400(self):
        stranger = Artist.objects.create(name="Other Band")
        response = self.client.get(self._url(artist_id=stranger.id))
        self.assertEqual(response.status_code, 400)

    def test_unknown_album_is_404(self):
        self.assertEqual(self.client.get(self._url(album_id=9999)).status_code, 404)


class PodcastScreenTests(_Patched):
    patches = staticmethod(lambda: ())

    def setUp(self):
        super().setUp()
        self.show = PodcastShow.objects.create(
            podcast_uuid="show-uuid-1",
            source="pocketcasts",
            title="Test Cast",
            author="Host",
            language="en",
            description="About things.",
            rss_feed_url="https://feed.example/rss",
        )
        base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        for number in range(1, 46):
            PodcastEpisode.objects.create(
                show=self.show,
                episode_uuid=f"ep-{number:02d}",
                title=f"Episode {number}",
                episode_number=number,
                published=base + timedelta(days=number),
                duration=1800,
            )
        self.refresh = patch("app.fork_services_podcast.refresh_show_from_rss")
        self.refresh_mock = self.refresh.start()
        self.addCleanup(self.refresh.stop)

    def _url(self, source="pocketcasts", uuid="show-uuid-1"):
        return reverse(
            "api_podcast_screen", kwargs={"source": source, "podcast_uuid": uuid}
        )

    def test_first_page_refreshes_the_feed_once(self):
        episode = PodcastEpisode.objects.get(show=self.show, episode_uuid="ep-45")
        fork_services_podcast.record_podcast_play(
            self.user, self.show, episode=episode, episode_uuid="ep-45", end_date=FIRST
        )
        response = self.client.get(self._url())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.refresh_mock.call_count, 1)
        data = response.json()
        self.assertEqual(data["show"]["uuid"], "show-uuid-1")
        self.assertEqual(data["show"]["title"], "Test Cast")
        self.assertEqual(data["show"]["id"], self.show.id)
        self.assertEqual(
            {row["label"] for row in data["details"]}, {"Author", "Language"}
        )
        page = data["episodes"]
        self.assertEqual(page["total"], 45)
        self.assertTrue(page["has_more"])
        self.assertEqual(page["next_page"], 2)
        self.assertEqual(len(page["episodes"]), 20)
        newest = page["episodes"][0]
        self.assertEqual(newest["uuid"], "ep-45")
        self.assertEqual(newest["id"], episode.id)
        self.assertEqual(newest["play_count"], 1)
        self.assertEqual(newest["plays"][0]["end_date"], FIRST.isoformat())
        self.assertEqual(page["episodes"][1]["plays"], [])

    def test_episode_page_does_not_refresh_and_returns_the_page(self):
        response = self.client.get(self._url() + "?episode_page=2")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.refresh_mock.call_count, 0)
        data = response.json()
        self.assertEqual(set(data), {"episodes", "total", "has_more", "next_page"})
        self.assertEqual(
            [row["uuid"] for row in data["episodes"]],
            [f"ep-{number:02d}" for number in range(25, 5, -1)],
        )
        self.assertTrue(data["has_more"])
        self.assertEqual(data["next_page"], 3)
        last = self.client.get(self._url() + "?episode_page=3").json()
        self.assertEqual(len(last["episodes"]), 5)
        self.assertFalse(last["has_more"])
        self.assertIsNone(last["next_page"])
        self.assertEqual(self.refresh_mock.call_count, 0)

    def test_invalid_episode_page_is_the_first_page(self):
        data = self.client.get(self._url() + "?episode_page=abc").json()
        self.assertEqual(data["show"]["uuid"], "show-uuid-1")
        self.assertEqual(self.refresh_mock.call_count, 1)

    def test_another_users_plays_are_not_shown(self):
        other = get_user_model().objects.create_user(username="other", password="x")
        episode = PodcastEpisode.objects.get(show=self.show, episode_uuid="ep-45")
        fork_services_podcast.record_podcast_play(
            other, self.show, episode=episode, episode_uuid="ep-45", end_date=FIRST
        )
        data = self.client.get(self._url()).json()
        self.assertEqual(data["episodes"]["episodes"][0]["plays"], [])

    def test_history_id_is_what_the_delete_endpoint_removes(self):
        episode = PodcastEpisode.objects.get(show=self.show, episode_uuid="ep-45")
        fork_services_podcast.record_podcast_play(
            self.user, self.show, episode=episode, episode_uuid="ep-45", end_date=FIRST
        )
        play = self.client.get(self._url()).json()["episodes"]["episodes"][0]["plays"][
            0
        ]
        response = self.client.delete(f"/api/v1/history/podcast/{play['history_id']}/")
        self.assertEqual(response.status_code, 204)
        again = self.client.get(self._url()).json()
        self.assertEqual(again["episodes"]["episodes"][0]["play_count"], 0)

    def test_deleting_the_latest_episode_play_moves_the_row_back(self):
        episode = PodcastEpisode.objects.get(show=self.show, episode_uuid="ep-45")
        for end_date in (FIRST, SECOND):
            fork_services_podcast.record_podcast_play(
                self.user,
                self.show,
                episode=episode,
                episode_uuid="ep-45",
                end_date=end_date,
            )
        podcast = Podcast.objects.get(user=self.user, episode=episode)
        record = podcast.history.get(end_date=SECOND)
        response = self.client.delete(f"/api/v1/history/podcast/{record.history_id}/")
        self.assertEqual(response.status_code, 204)
        podcast.refresh_from_db()
        self.assertEqual(podcast.end_date, FIRST)

    def test_unsupported_source_is_400(self):
        self.assertEqual(self.client.get(self._url(source="tmdb")).status_code, 400)

    def test_unknown_show_is_404(self):
        self.assertEqual(self.client.get(self._url(uuid="nope")).status_code, 404)
