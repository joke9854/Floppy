"""The season page's episode rating popup is built on demand, not per row.

Each episode row used to ship a full popup: ten star buttons with their own
hx-post, CSRF header and hx-vals. The popup now holds one URL per row and
builds its stars in Alpine when it opens.
"""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.models import TV, Episode, Item, MediaTypes, Season, Sources, Status

EPISODE_COUNT = 20
MEDIA_ID = "rating_markup_show"
SEASON_NUMBER = 1


class SeasonEpisodeRatingMarkupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ratingmarkup",
            password="12345",
        )
        cls.user.tv_enabled = True
        cls.user.save()
        air = datetime(2020, 1, 1, tzinfo=UTC)
        tv_item = Item.objects.create(
            media_id=MEDIA_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Rating Markup Show",
            image="https://example.com/show.jpg",
            release_datetime=air,
        )
        tv = TV.objects.create(
            item=tv_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )
        season_item = Item.objects.create(
            media_id=MEDIA_ID,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=SEASON_NUMBER,
            title="Rating Markup Show",
            image="https://example.com/season.jpg",
            release_datetime=air,
        )
        cls.season = Season.objects.create(
            item=season_item,
            related_tv=tv,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )
        Episode.objects.bulk_create(
            [
                Episode(
                    item=Item.objects.create(
                        media_id=MEDIA_ID,
                        source=Sources.TMDB.value,
                        media_type=MediaTypes.EPISODE.value,
                        season_number=SEASON_NUMBER,
                        episode_number=number,
                        title=f"Episode {number}",
                        image="https://example.com/episode.jpg",
                        release_datetime=air + timedelta(days=number),
                        runtime_minutes=25,
                    ),
                    related_season=cls.season,
                    end_date=air + timedelta(days=number),
                )
                for number in range(1, EPISODE_COUNT + 1)
            ],
        )

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    @patch("app.providers.trakt.is_configured", return_value=False)
    @patch("app.providers.services.get_media_metadata")
    def test_v2_season_rows_render_only_the_check(
        self,
        mock_metadata,
        _trakt_configured,
    ):
        episodes = [
            {
                "episode_number": number,
                "name": f"Episode {number}",
                "air_date": f"2020-01-{number:02d}",
                "runtime": 25,
                "vote_average": 7.5,
                "vote_count": 100,
            }
            for number in range(1, EPISODE_COUNT + 1)
        ]
        payload = {
            "title": "Rating Markup Show",
            "media_id": MEDIA_ID,
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "image": "https://example.com/show.jpg",
            f"season/{SEASON_NUMBER}": {
                "title": "Rating Markup Show",
                "season_title": f"Season {SEASON_NUMBER}",
                "media_id": MEDIA_ID,
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "season_number": SEASON_NUMBER,
                "image": "https://example.com/season.jpg",
                "episodes": episodes,
            },
        }
        # The view rewrites the metadata it is given, so each request needs its own copy.
        mock_metadata.side_effect = lambda *args, **kwargs: deepcopy(payload)

        url = reverse(
            "season_details",
            kwargs={
                "source": Sources.TMDB.value,
                "media_id": MEDIA_ID,
                "title": "rating-markup-show",
                "season_number": SEASON_NUMBER,
            },
        )
        response = self.client.get(f"{url}?fragment=secondary")

        self.assertEqual(response.status_code, 200)
        # v2 rows show only the check (detail.css hides the rest), so the
        # lists button and rating popup are not rendered at all.
        self.assertContains(response, 'id="episode-track-button-', count=EPISODE_COUNT)
        self.assertNotContains(response, 'title="Rate episode"')
        self.assertNotContains(response, "listsOpen")
