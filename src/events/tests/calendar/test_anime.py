import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase

from events.calendar.anime import get_anime_schedule_bulk, process_anime_bulk
from events.models import UNKNOWN_RELEASED_DATETIME
from events.tests.calendar.utils import CalendarFixturesMixin


class CalendarAnimeTests(CalendarFixturesMixin, TestCase):
    """Test anime calendar processing."""

    @patch("events.calendar.anime.services.api_request")
    def test_get_anime_schedule_bulk(self, mock_api_request):
        """Test the ordinary one-page AniList schedule."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [
                        {
                            "idMal": 437,
                            "airingSchedule": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {"episode": 1, "airingAt": 870739200},
                                ],
                            },
                        },
                    ],
                },
            },
        }

        result = get_anime_schedule_bulk(["437"])

        self.assertEqual(
            result["437"],
            [{"episode": 1, "airingAt": 870739200}],
        )
        self.assertEqual(mock_api_request.call_count, 1)
        self.assertEqual(
            mock_api_request.call_args.kwargs["params"]["variables"],
            {"ids": ["437"], "page": 1, "airingPage": 1},
        )
        query = mock_api_request.call_args.kwargs["params"]["query"]
        self.assertNotIn("\n          episodes\n", query)

    @patch("events.calendar.anime.services.get_media_metadata")
    @patch("events.calendar.anime.services.api_request")
    def test_get_anime_schedule_bulk_pages_and_deduplicates_without_total(
        self,
        mock_api_request,
        mock_get_media_metadata,
    ):
        """Read every nested page without requiring an aggregate episode total."""

        def anilist_response(*_args, **kwargs):
            airing_page = kwargs["params"]["variables"]["airingPage"]
            if airing_page == 1:
                nodes = [
                    {"episode": 2, "airingAt": None},
                    {"episode": 1, "airingAt": 1748736000},
                ]
            else:
                nodes = [
                    {"episode": 2, "airingAt": 1749340800},
                    {"episode": 3, "airingAt": 1749945600},
                    {"episode": 3, "airingAt": 1749945600},
                ]

            return {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": False},
                        "media": [
                            {
                                "idMal": 55809,
                                "airingSchedule": {
                                    "pageInfo": {
                                        "hasNextPage": airing_page == 1,
                                    },
                                    "nodes": nodes,
                                },
                            },
                        ],
                    },
                },
            }

        mock_api_request.side_effect = anilist_response

        result = get_anime_schedule_bulk(["55809"])

        self.assertEqual(
            result["55809"],
            [
                {"episode": 1, "airingAt": 1748736000},
                {"episode": 2, "airingAt": 1749340800},
                {"episode": 3, "airingAt": 1749945600},
            ],
        )
        self.assertEqual(mock_api_request.call_count, 2)
        self.assertEqual(
            [
                call.kwargs["params"]["variables"]["airingPage"]
                for call in mock_api_request.call_args_list
            ],
            [1, 2],
        )
        mock_get_media_metadata.assert_not_called()

    @patch("events.calendar.anime.services.api_request")
    def test_get_anime_schedule_bulk_pages_outer_and_nested_independently(
        self,
        mock_api_request,
    ):
        """Nested pagination finishes before the next outer media page."""

        def anilist_response(*_args, **kwargs):
            variables = kwargs["params"]["variables"]
            page = variables["page"]
            airing_page = variables["airingPage"]

            if page == 1:
                nodes = [
                    {
                        "episode": airing_page,
                        "airingAt": 1748736000 + (airing_page - 1) * 604800,
                    },
                ]
                media = [
                    {
                        "idMal": 100,
                        "airingSchedule": {
                            "pageInfo": {"hasNextPage": airing_page == 1},
                            "nodes": nodes,
                        },
                    },
                ]
                outer_has_next = True
            else:
                media = [
                    {
                        "idMal": 200,
                        "airingSchedule": {
                            "pageInfo": {"hasNextPage": False},
                            "nodes": [
                                {"episode": 1, "airingAt": 1760000000},
                            ],
                        },
                    },
                ]
                outer_has_next = False

            return {
                "data": {
                    "Page": {
                        "pageInfo": {"hasNextPage": outer_has_next},
                        "media": media,
                    },
                },
            }

        mock_api_request.side_effect = anilist_response

        result = get_anime_schedule_bulk(["100", "200"])

        self.assertEqual(
            [episode["episode"] for episode in result["100"]],
            [1, 2],
        )
        self.assertEqual(
            result["200"],
            [{"episode": 1, "airingAt": 1760000000}],
        )
        self.assertEqual(mock_api_request.call_count, 3)
        self.assertEqual(
            [
                (
                    call.kwargs["params"]["variables"]["page"],
                    call.kwargs["params"]["variables"]["airingPage"],
                )
                for call in mock_api_request.call_args_list
            ],
            [(1, 1), (1, 2), (2, 1)],
        )

    @patch("events.calendar.anime.services.get_media_metadata")
    @patch("events.calendar.anime.services.api_request")
    def test_get_anime_schedule_bulk_keeps_explicit_schedule_nodes(
        self,
        mock_api_request,
        mock_get_media_metadata,
    ):
        """Do not use an aggregate count or fallback provider to remove nodes."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [
                        {
                            "idMal": 437,
                            "airingSchedule": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {"episode": 1, "airingAt": 870739200},
                                    {"episode": 2, "airingAt": 870825600},
                                ],
                            },
                        },
                    ],
                },
            },
        }

        result = get_anime_schedule_bulk(["437"])

        self.assertEqual(
            result["437"],
            [
                {"episode": 1, "airingAt": 870739200},
                {"episode": 2, "airingAt": 870825600},
            ],
        )
        mock_get_media_metadata.assert_not_called()

    @patch("events.calendar.anime.services.api_request")
    def test_process_anime_bulk(self, mock_api_request):
        """Test process_anime_bulk function."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [
                        {
                            "idMal": 437,
                            "airingSchedule": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [
                                    {"episode": 1, "airingAt": 870739200},
                                ],
                            },
                        },
                    ],
                },
            },
        }

        events_bulk = []
        checked = process_anime_bulk([self.anime_item], events_bulk)

        self.assertEqual(checked, [self.anime_item])
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.anime_item)
        self.assertEqual(events_bulk[0].content_number, 1)

        expected_date = datetime.datetime.fromtimestamp(870739200, tz=ZoneInfo("UTC"))
        self.assertEqual(events_bulk[0].datetime, expected_date)

    @patch("events.calendar.anime.services.api_request")
    def test_process_anime_bulk_preserves_unknown_airing_date(self, mock_api_request):
        """Keep the current year-1 unknown released-date representation."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [
                        {
                            "idMal": 437,
                            "airingSchedule": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [{"episode": 1, "airingAt": None}],
                            },
                        },
                    ],
                },
            },
        }

        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)

        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(
            events_bulk[0].datetime,
            UNKNOWN_RELEASED_DATETIME,
        )

    @patch("events.calendar.anime.process_other")
    @patch("events.calendar.anime.services.api_request")
    def test_process_anime_bulk_does_not_fallback_for_matched_empty_schedule(
        self,
        mock_api_request,
        mock_process_other,
    ):
        """A matched AniList item with no nodes is not a synthetic MAL event."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [
                        {
                            "idMal": 437,
                            "airingSchedule": {
                                "pageInfo": {"hasNextPage": False},
                                "nodes": [],
                            },
                        },
                    ],
                },
            },
        }

        events_bulk = []
        checked = process_anime_bulk([self.anime_item], events_bulk)

        self.assertEqual(checked, [self.anime_item])
        self.assertEqual(events_bulk, [])
        mock_process_other.assert_not_called()

    @patch("events.calendar.anime.services.get_media_metadata")
    @patch("events.calendar.anime.services.api_request")
    def test_process_anime_bulk_no_matching_anime_anilist(
        self,
        mock_api_request,
        mock_get_media_metadata,
    ):
        """Keep the existing MAL fallback when AniList has no matching media."""
        mock_api_request.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [],
                },
            },
        }
        mock_get_media_metadata.return_value = {
            "max_progress": 1,
            "details": {"end_date": "1997-08-05"},
        }

        events_bulk = []
        checked = process_anime_bulk([self.anime_item], events_bulk)

        self.assertEqual(checked, [self.anime_item])
        self.assertEqual(len(events_bulk), 1)
