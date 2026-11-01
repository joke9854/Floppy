import re
from datetime import UTC, datetime

from django.db import models
from django.db.models import (
    Case,
    Exists,
    IntegerField,
    OuterRef,
    Q,
    UniqueConstraint,
    Value,
    When,
)
from django.utils import timezone

from app import config
from app.models import TV, Item, MediaTypes, Season, Sources, Status
from app.services.item_merge import dedupe_cross_provider_items
from integrations.anime_mapping import resolve_provider_series_id

# Explicit unknown-date sentinels. Both stay inside the datetime range after
# conversion to any UTC offset (+-14h), unlike datetime.min/max, which overflow
# when localized.
UNKNOWN_RELEASED_DATETIME = datetime(1, 1, 2, 11, 59, 59, 999999, tzinfo=UTC)
UNKNOWN_UNRELEASED_DATETIME = datetime(9999, 12, 30, 11, 59, 59, 999999, tzinfo=UTC)
# Values written before the explicit sentinels existed. A legacy year-1 value
# meant "undated" for TV seasons (not yet aired) and "released, no date" for
# everything else.
LEGACY_UNKNOWN_DATETIME = datetime.min.replace(tzinfo=UTC)
LEGACY_UNKNOWN_UNRELEASED_DATETIMES = (
    datetime.max.replace(tzinfo=UTC),
    datetime(9999, 12, 31, 23, 59, 59, tzinfo=UTC),
)
UNKNOWN_EVENT_DATETIMES = (
    UNKNOWN_RELEASED_DATETIME,
    UNKNOWN_UNRELEASED_DATETIME,
    LEGACY_UNKNOWN_DATETIME,
    *LEGACY_UNKNOWN_UNRELEASED_DATETIMES,
)
UNKNOWN_UNRELEASED_QUERY = Q(
    datetime__in=(UNKNOWN_UNRELEASED_DATETIME, *LEGACY_UNKNOWN_UNRELEASED_DATETIMES),
) | Q(item__media_type=MediaTypes.SEASON.value, datetime=LEGACY_UNKNOWN_DATETIME)

# Statuses that represent inactive tracking
# will be ignored when creating events
INACTIVE_TRACKING_STATUSES = [
    Status.PAUSED.value,
    Status.DROPPED.value,
]


_SEASON_PART_SUFFIX_RE = re.compile(r"(?i)\b(season|part|cour)\b.*$")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _normalize_anime_title(title: str) -> str:
    """Strip season/part suffixes and punctuation for an exact-match fallback."""
    stripped = _SEASON_PART_SUFFIX_RE.sub("", title)
    return _NON_ALNUM_RE.sub("", stripped.lower())


class SentinelDatetime:
    """Sentinel time for event without a specific time."""

    YEAR = 9999
    MONTH = 12
    DAY = 31
    HOUR = 11
    MINUTE = 59
    SECOND = 59
    MICROSECOND = 999999


class EventManager(models.Manager):
    """Custom manager for the Event model."""

    def get_user_events(self, user, first_day, last_day):
        """Get all upcoming media events of the specified user."""
        start_datetime = timezone.make_aware(
            datetime.combine(first_day, datetime.min.time()),
        )
        end_datetime = timezone.make_aware(
            datetime.combine(last_day, datetime.max.time()),
        )

        enabled_types = user.get_enabled_media_types()
        non_tv_types = [
            media_type
            for media_type in enabled_types
            if media_type not in [MediaTypes.TV.value, MediaTypes.SEASON.value]
        ]

        # Build base query for non-TV media types
        user_query = Q()
        active_status_query = Q()

        for media_type in non_tv_types:
            user_query |= Q(**{f"item__{media_type}__user": user})
            active_status_query &= ~Q(
                **{f"item__{media_type}__status__in": INACTIVE_TRACKING_STATUSES},
            )

        tv_query = self._build_tv_query(user, enabled_types)
        combined_query = (user_query & active_status_query) | tv_query

        queryset = self.filter(
            combined_query,
            datetime__gte=start_datetime,
            datetime__lte=end_datetime,
        ).exclude(datetime__in=UNKNOWN_EVENT_DATETIMES).select_related("item")

        hidden_item_ids = self.hidden_duplicate_item_ids(user, enabled_types)
        if hidden_item_ids:
            queryset = queryset.exclude(item_id__in=hidden_item_ids)

        return self.sort_with_sentinel_last(queryset)

    def hidden_duplicate_item_ids(self, user, enabled_types):
        """Return `Item` ids to exclude because a preferred duplicate exists.

        Combines the TMDB/TVDB cross-provider dedup (#639) with the
        Anime/TV cross-bucket dedup (#968), so both the calendar and
        release notifications hide the same duplicates.
        """
        return self._cross_provider_hidden_season_item_ids(
            user,
            enabled_types,
        ) | self._cross_bucket_hidden_anime_item_ids(
            user,
            enabled_types,
        )

    def _active_tv_show_media_ids(self, user):
        """Return media_ids of the user's actively-tracked TV shows, deduped across providers."""
        items = list(
            Item.objects.filter(
                tv__user=user,
                media_type=MediaTypes.TV.value,
            ).exclude(tv__status__in=INACTIVE_TRACKING_STATUSES),
        )
        if not items:
            return []

        preferred_source = getattr(
            user,
            "tv_metadata_source_default",
            Sources.TMDB.value,
        )
        deduped = dedupe_cross_provider_items(items, preferred_source)
        return [item.media_id for item in deduped]

    def _cross_provider_hidden_season_item_ids(self, user, enabled_types):
        """Return Season `Item` ids to hide because a preferred counterpart exists.

        A user can legitimately track the same show under both a TMDB and a
        TVDB identity (the #620 dual-identity model); each identity gets its
        own independent Season `Item`s and `Event`s. Without this, the
        calendar shows the same real episode twice - once per identity
        (#639). Uses the same verified cached cross-provider mapping already
        used for Home rows; Season rows fall back to their matching TMDB TV
        item's mapping when the child row has no `tvdb_id` of its own.
        """
        if not (
            MediaTypes.TV.value in enabled_types
            or MediaTypes.SEASON.value in enabled_types
        ):
            return set()

        active_tv_shows = self._active_tv_show_media_ids(user)
        if not active_tv_shows:
            return set()

        season_items = list(
            Item.objects.filter(
                media_type=MediaTypes.SEASON.value,
                media_id__in=active_tv_shows,
            ),
        )
        if not season_items:
            return set()

        preferred_source = getattr(
            user,
            "tv_metadata_source_default",
            Sources.TMDB.value,
        )
        deduped = dedupe_cross_provider_items(season_items, preferred_source)
        if len(deduped) == len(season_items):
            return set()

        kept_ids = {item.id for item in deduped}
        return {item.id for item in season_items if item.id not in kept_ids}

    def _cross_bucket_hidden_anime_item_ids(self, user, enabled_types):
        """Return Anime `Item` ids to hide because a tracked TV counterpart exists.

        A user can track the same real show both in the Anime bucket (MAL)
        and the TV bucket (TMDB/TVDB) - each gets its own independent `Item`
        and `Event`s, so without this the calendar and release notifications
        fire twice for the same episode (#968). Uses the pinned Kometa
        Anime-IDs mapping (`integrations.anime_mapping`) to resolve a MAL id
        to its verified TMDB/TVDB series id. Newly announced anime aren't in
        that static snapshot yet (#1000), so as a guarded fallback - only
        when the verified lookup misses, and only against the user's own
        actively-tracked shows, never the global DB - an anime item whose
        normalized title exactly matches a tracked TV show's is also hidden.
        The TV bucket is always kept since it carries season/episode
        structure; the Anime bucket duplicate is hidden.
        """
        if MediaTypes.ANIME.value not in enabled_types:
            return set()
        if not (
            MediaTypes.TV.value in enabled_types
            or MediaTypes.SEASON.value in enabled_types
        ):
            return set()

        active_anime_items = list(
            Item.objects.filter(
                media_type=MediaTypes.ANIME.value,
                source=Sources.MAL.value,
                anime__user=user,
            ).exclude(anime__status__in=INACTIVE_TRACKING_STATUSES),
        )
        if not active_anime_items:
            return set()

        active_tv_rows = list(
            TV.objects.filter(
                user=user,
                item__media_type=MediaTypes.TV.value,
            )
            .exclude(status__in=INACTIVE_TRACKING_STATUSES)
            .values_list("item__source", "item__media_id", "item__title"),
        )
        if not active_tv_rows:
            return set()

        active_tv_shows = {(source, media_id) for source, media_id, _ in active_tv_rows}
        active_tv_title_slugs = {
            slug
            for _, _, title in active_tv_rows
            if (slug := _normalize_anime_title(title))
        }

        hidden_ids = set()
        for anime_item in active_anime_items:
            tmdb_id = resolve_provider_series_id(anime_item.media_id, "tmdb")
            tvdb_id = resolve_provider_series_id(anime_item.media_id, "tvdb")
            has_verified_match = (
                tmdb_id and (Sources.TMDB.value, tmdb_id) in active_tv_shows
            ) or (tvdb_id and (Sources.TVDB.value, tvdb_id) in active_tv_shows)
            title_slug = _normalize_anime_title(anime_item.title)
            has_title_fallback_match = title_slug and title_slug in active_tv_title_slugs
            if has_verified_match or has_title_fallback_match:
                hidden_ids.add(anime_item.id)

        return hidden_ids

    def _build_tv_query(self, user, enabled_types):
        """Build query for TV shows based on TV status and season statuses."""
        if not (
            MediaTypes.TV.value in enabled_types
            or MediaTypes.SEASON.value in enabled_types
        ):
            return Q()

        # Get active TV shows
        active_tv_shows = self._active_tv_show_media_ids(user)

        if not active_tv_shows:
            return Q()

        # A dropped/paused season hides itself and every later season of the
        # same show. Checking "does an inactive season at or before this
        # season's number exist" via a correlated Exists avoids compiling one
        # OR clause per active show with a dropped season.
        dropped_season_exists = Exists(
            Season.objects.filter(
                user=user,
                item__media_id=OuterRef("item__media_id"),
                status__in=INACTIVE_TRACKING_STATUSES,
                item__season_number__lte=OuterRef("item__season_number"),
            ),
        )

        return (
            Q(
                item__media_type=MediaTypes.SEASON.value,
                item__media_id__in=active_tv_shows,
            )
            & ~Q(dropped_season_exists)
        )

    def sort_with_sentinel_last(self, queryset):
        """Sort events with sentinel time last."""
        today = timezone.now().date()
        sentinel_dt = timezone.localtime(
            datetime(
                today.year,
                today.month,
                today.day,
                SentinelDatetime.HOUR,
                SentinelDatetime.MINUTE,
                SentinelDatetime.SECOND,
                SentinelDatetime.MICROSECOND,
                tzinfo=UTC,
            ),
        )

        return queryset.annotate(
            is_sentinel=Case(
                When(
                    datetime__hour=sentinel_dt.hour,
                    datetime__minute=sentinel_dt.minute,
                    datetime__second=sentinel_dt.second,
                    then=Value(1),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
        ).order_by("datetime__date", "is_sentinel", "datetime")


class Event(models.Model):
    """Calendar event model."""

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    content_number = models.IntegerField(null=True)
    datetime = models.DateTimeField()
    notification_sent = models.BooleanField(default=False)
    objects = EventManager()

    class Meta:
        """Meta class for Event model."""

        ordering = ["-datetime"]
        constraints = [
            UniqueConstraint(
                fields=["item", "content_number"],
                name="unique_item_content_number",
            ),
            UniqueConstraint(
                fields=["item"],
                condition=Q(content_number__isnull=True),
                name="unique_item_null_content_number",
            ),
        ]

    def __str__(self):
        """Return event title."""
        if self.content_number:
            return (
                f"{self.item.__str__()} "
                f"{config.get_unit(self.item.media_type, short=True)}"
                f"{self.content_number}"
            )

        return self.item.__str__()

    @property
    def readable_content_number(self):
        """Return the episode number in a readable format."""
        if self.content_number is None:
            return ""

        return (
            f"{config.get_unit(self.item.media_type, short=True)}{self.content_number}"
        )

    @property
    def is_sentinel_time(self):
        """Check if the event time is sentinel time."""
        return (
            self.datetime.hour == SentinelDatetime.HOUR
            and self.datetime.minute == SentinelDatetime.MINUTE
            and self.datetime.second == SentinelDatetime.SECOND
            and self.datetime.microsecond == SentinelDatetime.MICROSECOND
        )

    @property
    def is_max_datetime(self):
        """Compatibility alias for unknown and unreleased events."""
        return self.is_unknown_unreleased

    @property
    def is_unknown_released(self):
        """Return whether this is released content without a known date."""
        if self.datetime == UNKNOWN_RELEASED_DATETIME:
            return True
        return (
            self.datetime == LEGACY_UNKNOWN_DATETIME
            and self.item.media_type != MediaTypes.SEASON.value
        )

    @property
    def is_unknown_unreleased(self):
        """Return whether this content has no known release date yet."""
        if self.datetime in (
            UNKNOWN_UNRELEASED_DATETIME,
            *LEGACY_UNKNOWN_UNRELEASED_DATETIMES,
        ):
            return True
        return (
            self.datetime == LEGACY_UNKNOWN_DATETIME
            and self.item.media_type == MediaTypes.SEASON.value
        )
