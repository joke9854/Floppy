"""Report known and ambiguous calendar boundary values without changing data."""

from datetime import UTC, datetime

from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models import Count, Q

from app.models import Item
from events.models import (
    LEGACY_UNKNOWN_DATETIME,
    LEGACY_UNKNOWN_UNRELEASED_DATETIMES,
    UNKNOWN_RELEASED_DATETIME,
    UNKNOWN_UNRELEASED_DATETIME,
    Event,
)

SAMPLE_LIMIT = 10
UPSTREAM_UNKNOWN_RELEASED_DATETIME = datetime(
    1,
    1,
    1,
    11,
    59,
    59,
    999999,
    tzinfo=UTC,
)
UPSTREAM_UNKNOWN_UNRELEASED_DATETIME = datetime(
    9999,
    12,
    31,
    11,
    59,
    59,
    999999,
    tzinfo=UTC,
)


class Command(BaseCommand):
    """Inventory calendar sentinel values for a later data migration."""

    help = "Audit calendar sentinel values without changing data"

    def handle(self, *_args, **_options):
        """Print a deterministic, privacy-safe inventory."""
        known_released = (
            UNKNOWN_RELEASED_DATETIME,
            LEGACY_UNKNOWN_DATETIME,
            UPSTREAM_UNKNOWN_RELEASED_DATETIME,
        )
        known_unreleased = (
            UNKNOWN_UNRELEASED_DATETIME,
            *LEGACY_UNKNOWN_UNRELEASED_DATETIMES,
            UPSTREAM_UNKNOWN_UNRELEASED_DATETIME,
        )
        targets = (
            (
                "event",
                "datetime",
                Event.objects.all(),
                "item__media_type",
            ),
            (
                "item",
                "release_datetime",
                Item.objects.filter(
                    pk__in=Event.objects.order_by().values("item_id"),
                ),
                "media_type",
            ),
        )

        self.stdout.write(f"backend={connection.vendor} sample_limit={SAMPLE_LIMIT}")
        for record, field, queryset, media_field in targets:
            categories = (
                (
                    "legacy_min",
                    Q(**{field: LEGACY_UNKNOWN_DATETIME}),
                ),
                (
                    "upstream_safe_min",
                    Q(**{field: UPSTREAM_UNKNOWN_RELEASED_DATETIME}),
                ),
                (
                    "floppy_safe_min",
                    Q(**{field: UNKNOWN_RELEASED_DATETIME}),
                ),
                (
                    "ambiguous_year_1",
                    Q(
                        **{
                            f"{field}__gte": datetime(1, 1, 1, tzinfo=UTC),
                            f"{field}__lt": datetime(2, 1, 1, tzinfo=UTC),
                        },
                    )
                    & ~Q(**{f"{field}__in": known_released}),
                ),
                (
                    "floppy_safe_max",
                    Q(**{field: UNKNOWN_UNRELEASED_DATETIME}),
                ),
                (
                    "upstream_safe_max",
                    Q(**{field: UPSTREAM_UNKNOWN_UNRELEASED_DATETIME}),
                ),
                (
                    "legacy_max",
                    Q(
                        **{
                            f"{field}__in": LEGACY_UNKNOWN_UNRELEASED_DATETIMES,
                        },
                    ),
                ),
                (
                    "ambiguous_year_9999",
                    Q(
                        **{
                            f"{field}__gte": datetime(9999, 1, 1, tzinfo=UTC),
                            f"{field}__lte": datetime.max.replace(tzinfo=UTC),
                        },
                    )
                    & ~Q(**{f"{field}__in": known_unreleased}),
                ),
            )
            for name, criteria in categories:
                self._write_category(
                    record,
                    field,
                    name,
                    queryset.filter(criteria),
                    media_field,
                )

    def _write_category(self, record, field, name, queryset, media_field):
        """Print count, deterministic media counts, and bounded primary keys."""
        count = queryset.count()
        media_types = ",".join(
            f"{row[media_field]}:{row['count']}"
            for row in queryset.order_by()
            .values(media_field)
            .annotate(count=Count("pk"))
            .order_by(media_field)
        )
        sample_pks = ",".join(
            str(pk)
            for pk in queryset.order_by("pk").values_list("pk", flat=True)[
                :SAMPLE_LIMIT
            ]
        )
        self.stdout.write(
            f"record={record} field={field} category={name} total={count} "
            f"media_types={media_types or '-'} "
            f"sample_pks={sample_pks or '-'}",
        )
