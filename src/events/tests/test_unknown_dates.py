"""Unknown-date semantics for calendar events (adapted from dannyvfilms PR #683)."""

from io import StringIO
from zoneinfo import ZoneInfo

from django.core.management import call_command
from django.test import TestCase

from app.models import Item, MediaTypes, Sources
from events.admin import EventAdmin
from events.models import (
    LEGACY_UNKNOWN_DATETIME,
    UNKNOWN_EVENT_DATETIMES,
    UNKNOWN_RELEASED_DATETIME,
    UNKNOWN_UNRELEASED_DATETIME,
    UNKNOWN_UNRELEASED_QUERY,
    Event,
)


class UnknownDateSemanticsTests(TestCase):
    """Released and unreleased unknown dates stay distinct and overflow-safe."""

    def setUp(self):
        """Create one season item and one anime item."""
        self.season_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Show",
            season_number=1,
        )
        self.anime_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Anime",
        )

    def test_sentinels_survive_every_utc_offset(self):
        """Neither sentinel overflows when localized to UTC-12 or UTC+14."""
        for zone in ("Etc/GMT+12", "Pacific/Kiritimati"):
            for value in (UNKNOWN_RELEASED_DATETIME, UNKNOWN_UNRELEASED_DATETIME):
                value.astimezone(ZoneInfo(zone))

    def test_legacy_year_one_means_unreleased_only_for_seasons(self):
        """Old datetime.min rows: undated TV episode vs released other media."""
        season_event = Event(item=self.season_item, datetime=LEGACY_UNKNOWN_DATETIME)
        anime_event = Event(item=self.anime_item, datetime=LEGACY_UNKNOWN_DATETIME)

        self.assertTrue(season_event.is_unknown_unreleased)
        self.assertFalse(season_event.is_unknown_released)
        self.assertTrue(anime_event.is_unknown_released)
        self.assertFalse(anime_event.is_unknown_unreleased)

    def test_unreleased_query_keeps_released_unknown_rows(self):
        """Readers exclude unknown/unreleased rows but still count released ones."""
        Event.objects.create(
            item=self.season_item,
            content_number=1,
            datetime=LEGACY_UNKNOWN_DATETIME,
        )
        Event.objects.create(
            item=self.season_item,
            content_number=2,
            datetime=UNKNOWN_UNRELEASED_DATETIME,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=1,
            datetime=UNKNOWN_RELEASED_DATETIME,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=2,
            datetime=LEGACY_UNKNOWN_DATETIME,
        )

        kept = Event.objects.exclude(UNKNOWN_UNRELEASED_QUERY)

        self.assertEqual(
            set(kept.values_list("item__media_type", "content_number")),
            {(MediaTypes.ANIME.value, 1), (MediaTypes.ANIME.value, 2)},
        )

    def test_next_event_alias_and_admin_label(self):
        """Cards hide unknown next events; the admin labels them, never localizes."""
        event = Event(item=self.season_item, datetime=UNKNOWN_UNRELEASED_DATETIME)
        admin = EventAdmin(Event, None)

        self.assertTrue(event.is_max_datetime)
        self.assertEqual(admin.formatted_datetime(event), "Unknown (unreleased)")
        self.assertIn("datetime", admin.get_exclude(None, event))

    def test_audit_command_reports_without_changing_data(self):
        """The audit counts each category and leaves every row untouched."""
        Event.objects.create(
            item=self.season_item,
            content_number=1,
            datetime=LEGACY_UNKNOWN_DATETIME,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=1,
            datetime=UNKNOWN_RELEASED_DATETIME,
        )
        before = list(Event.objects.order_by("pk").values_list("datetime", flat=True))

        out = StringIO()
        call_command("audit_calendar_sentinels", stdout=out)
        output = out.getvalue()

        self.assertIn("record=event field=datetime category=legacy_min total=1", output)
        self.assertIn(
            "record=event field=datetime category=floppy_safe_min total=1",
            output,
        )
        self.assertNotIn("Show", output)
        self.assertEqual(
            list(Event.objects.order_by("pk").values_list("datetime", flat=True)),
            before,
        )
