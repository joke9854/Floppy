from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import (
    Album,
    AlbumTracker,
    Artist,
    ArtistTracker,
    MediaTypes,
    PodcastShow,
    PodcastShowTracker,
    Sources,
    Status,
)
from app.providers import services
from users.models import MetadataSourceDefaultChoices


class MediaSearchViewTests(TestCase):
    """Test the media search view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.search")
    def test_search_without_query_parameters_renders(self, mock_search):
        """A bare /search falls back to the saved type and an empty query."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 0,
            "results": [],
        }

        response = self.client.get(reverse("search"))

        self.assertEqual(response.status_code, 200)

    @patch("app.providers.services.search")
    def test_media_search_view(self, mock_search):
        """Test the media search view."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "238",
                    "title": "Test Movie",
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                },
            ],
        }

        response = self.client.get(
            reverse("search") + "?media_type=movie&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_search_type, MediaTypes.MOVIE.value)

        mock_search.assert_called_once_with(
            MediaTypes.MOVIE.value,
            "test",
            1,
            Sources.TMDB.value,
            language="en",
            user=self.user,
        )

    @patch("app.providers.services.search")
    def test_search_result_track_modal_is_cloaked(self, mock_search):
        """The track modal must not flash before Alpine hides it.

        media_card_list.html's overlay is a full-screen
        `fixed inset-0 bg-black/50` div; without x-cloak it renders visible
        until Alpine boots and applies x-show="trackOpen".
        """
        mock_search.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "238",
                    "title": "Test Movie",
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                },
            ],
        }

        response = self.client.get(
            reverse("search") + "?media_type=movie&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response.content.decode(),
            r'x-show="trackOpen"[^>]*\sx-cloak\b',
        )

    @patch("app.providers.services.search")
    def test_podcast_local_result_keeps_show_source(self, mock_search):
        """Local podcast search results must not be mislabeled as Pocket Casts."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 0,
            "results": [],
        }
        show = PodcastShow.objects.create(
            podcast_uuid="gp_abc123",
            source=Sources.GPODDER.value,
            title="Gpodder Show",
        )
        PodcastShowTracker.objects.create(
            user=self.user, show=show, status=Status.IN_PROGRESS.value
        )

        response = self.client.get(
            reverse("search") + "?media_type=podcast&q=Gpodder",
        )

        self.assertEqual(response.status_code, 200)
        local_results = response.context["local_results"]
        self.assertEqual(len(local_results), 1)
        self.assertEqual(local_results[0]["item"].source, Sources.GPODDER.value)

    @patch("app.providers.services.search")
    def test_music_search_view_uses_shared_template(
        self,
        mock_search,
    ):
        """Music search should render grouped artist/album sections."""
        artist = Artist.objects.create(name="Pentatonix")
        album = Album.objects.create(
            title="Evergreen",
            artist=artist,
            image="http://example.com/local-album.jpg",
        )
        ArtistTracker.objects.create(user=self.user, artist=artist, score=8.5)
        AlbumTracker.objects.create(user=self.user, album=album, score=9.0)

        mock_search.return_value = {
            "artists": [
                {
                    "artist_id": "mb-artist-1",
                    "name": "Pentatonix",
                    "type": "Group",
                    "begin_year": "2011",
                    "disambiguation": "",
                    "image": "http://example.com/remote-artist.jpg",
                },
            ],
            "releases": [
                {
                    "release_id": "mb-release-1",
                    "title": "A Pentatonix Christmas",
                    "artist_name": "Pentatonix",
                    "release_date": "2016-10-21",
                    "image": "http://example.com/remote-album.jpg",
                },
            ],
            "tracks": {
                "page": 1,
                "total_results": 0,
                "total_pages": 0,
                "results": [],
            },
        }

        response = self.client.get(
            reverse("search") + "?media_type=music&q=Pentatonix",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")
        self.assertContains(response, "In Your Library")
        self.assertContains(response, "Online Results")
        self.assertContains(response, "Evergreen")
        self.assertContains(response, "A Pentatonix Christmas")
        self.assertContains(response, "Pentatonix")
        self.assertContains(
            response,
            reverse(
                "music_artist_details",
                kwargs={
                    "artist_id": artist.id,
                    "artist_slug": "pentatonix",
                },
            ),
        )
        self.assertContains(
            response,
            reverse(
                "music_album_details",
                kwargs={
                    "artist_id": artist.id,
                    "artist_slug": "pentatonix",
                    "album_id": album.id,
                    "album_slug": "evergreen",
                },
            ),
        )
        self.assertContains(response, "http://example.com/remote-artist.jpg")
        self.assertContains(response, "http://example.com/remote-album.jpg")
        self.assertNotIn("Tracks</h3>", response.content.decode())

        mock_search.assert_called_once_with(
            MediaTypes.MUSIC.value,
            "Pentatonix",
            1,
            Sources.MUSICBRAINZ.value,
            language="en",
            user=self.user,
        )

    @patch("app.providers.services.search")
    def test_music_local_album_search_matches_artist_name(self, mock_search):
        """Music local albums should include artist-name matches."""
        artist = Artist.objects.create(name="Pentatonix")
        album = Album.objects.create(title="The Lucky Ones", artist=artist)
        AlbumTracker.objects.create(user=self.user, album=album)

        mock_search.return_value = {
            "artists": [],
            "releases": [],
            "tracks": {
                "page": 1,
                "total_results": 0,
                "total_pages": 0,
                "results": [],
            },
        }

        response = self.client.get(
            reverse("search") + "?media_type=music&q=Pentatonix",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "The Lucky Ones")

    @override_settings(TVDB_API_KEY="test-tvdb-key")
    @patch("app.providers.services.search")
    def test_anime_search_defaults_to_user_metadata_provider(self, mock_search):
        """Anime search should honor the user's configured default metadata source."""
        self.user.anime_metadata_source_default = MetadataSourceDefaultChoices.TVDB
        self.user.save(update_fields=["anime_metadata_source_default"])
        mock_search.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 0,
            "results": [],
        }

        response = self.client.get(
            reverse("search") + "?media_type=anime&q=chainsaw",
        )

        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once_with(
            MediaTypes.ANIME.value,
            "chainsaw",
            1,
            Sources.TVDB.value,
            language="en",
            user=self.user,
        )

    @override_settings(HARDCOVER_API="")
    @patch("app.providers.services.search")
    def test_book_search_falls_back_to_open_library(self, mock_search):
        """Book search must work out of the box without a Hardcover key (#1025)."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 0,
            "results": [],
        }

        response = self.client.get(reverse("search") + "?media_type=book&q=quo+vadis")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args.args[3], Sources.OPENLIBRARY.value)
        self.assertNotIn(
            Sources.HARDCOVER,
            response.context["source_options"],
        )

    @override_settings(HARDCOVER_API="")
    @patch("app.providers.services.search")
    def test_an_explicit_hardcover_source_is_coerced(self, mock_search):
        """A bookmarked ?source=hardcover URL must not resurrect the dead path."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 0,
            "results": [],
        }

        response = self.client.get(
            reverse("search") + "?media_type=book&q=quo+vadis&source=hardcover",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_search.call_args.args[3], Sources.OPENLIBRARY.value)

    @patch("app.providers.services.search")
    def test_search_uses_interactive_request_scope(self, mock_search):
        """Rate-limit retries must fail fast, not block the request (#1001)."""

        def assert_interactive(*args, **kwargs):
            self.assertTrue(services._interactive_request.get())
            return {
                "page": 1,
                "total_results": 0,
                "total_pages": 0,
                "results": [],
            }

        mock_search.side_effect = assert_interactive

        response = self.client.get(
            reverse("search") + "?media_type=book&q=test",
        )

        self.assertEqual(response.status_code, 200)
        mock_search.assert_called_once()
        self.assertFalse(services._interactive_request.get())

    @patch("app.providers.services.search")
    def test_search_provider_error_renders_page_with_message(self, mock_search):
        """A provider failure (e.g. exhausted rate-limit retries) must not 500 (#1001)."""
        mock_search.side_effect = services.ProviderAPIError(
            Sources.HARDCOVER.value, Exception("boom")
        )

        response = self.client.get(
            reverse("search") + "?media_type=book&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertIn("Hardcover", str(messages[0]))
        self.assertIn("unavailable", str(messages[0]))
