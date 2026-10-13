"""Time CineTrack's episode re-send on this server without changing anything.

For each show, replays up to --batch of the user's stored plays through the
same function the CineTrack episode endpoint uses, with fresh event ids (as a
re-send from a new connection does), inside a transaction that is always
rolled back. It prints the total time, database time and query count, and the
stage timings: match_ms (plays found already stored), metadata_ms (TMDB
lookup) and tvdb_ms (TVDB identity matching).

A replay uses the coordinates Floppy stored, so it always takes the fast path.
--force-lookup adds one episode Floppy cannot match, which takes the slow path
a real initial sync takes for anime numbering or episodes Floppy cannot place.

Read-only for the library: nothing is committed. Provider responses fetched on
the slow path may be cached, as during normal use.
"""

import time
import uuid
from collections import Counter
from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

from api.cinetrack_bootstrap_views import EpisodeEnsureError, ensure_episode_events
from app.models import Episode, Sources
from app.providers import credentials

UNMATCHABLE_EPISODE = 9999
UNMATCHABLE_AT = datetime(2001, 1, 1, tzinfo=UTC)


class Command(BaseCommand):
    """Profile CineTrack episode re-sends."""

    help = __doc__.splitlines()[0]

    def add_arguments(self, parser):
        """Register options."""
        parser.add_argument("--user", required=True, help="Floppy username.")
        parser.add_argument("--show", action="append", default=[], help="TMDB show id (repeatable).")
        parser.add_argument("--shows", type=int, default=10, help="Without --show: the N shows with most plays.")
        parser.add_argument("--batch", type=int, default=50, help="Plays per request, like CineTrack (max 50).")
        parser.add_argument("--force-lookup", action="store_true", help="Add one unmatchable episode (slow path).")

    def handle(self, *args, **options):
        """Run the profile."""
        user = get_user_model().objects.filter(username=options["user"]).first()
        if user is None:
            msg = "No such user."
            raise CommandError(msg)
        batch = max(1, min(options["batch"], 50))
        if options["show"]:
            shows = options["show"]
        else:
            plays_per_show = Counter(
                Episode.objects.filter(
                    related_season__user=user,
                    related_season__item__source=Sources.TMDB.value,
                ).values_list("related_season__item__media_id", flat=True),
            )
            shows = [media_id for media_id, _count in plays_per_show.most_common(options["shows"])]
        seen = set()
        for media_id in shows:
            if media_id in seen:
                continue
            seen.add(media_id)
            self.profile(user, str(media_id), batch, force_lookup=options["force_lookup"])

    def profile(self, user, media_id, batch, *, force_lookup):
        """Replay one batch of one show and print where the time went."""
        rows = list(
            Episode.objects.filter(
                related_season__user=user,
                related_season__item__media_id=media_id,
                related_season__item__source=Sources.TMDB.value,
                end_date__isnull=False,
            )
            .select_related("related_season__item", "item")
            .order_by("end_date", "id")[:batch],
        )
        if not rows:
            self.stdout.write(f"show {media_id}: no plays")
            return
        parsed = [
            (row.related_season.item.season_number, row.item.episode_number, row.end_date, uuid.uuid4())
            for row in rows
        ]
        if force_lookup:
            parsed = [*parsed[: batch - 1], (parsed[0][0], UNMATCHABLE_EPISODE, UNMATCHABLE_AT, uuid.uuid4())]
        timings = {}
        outcomes = Counter()
        error = None
        started = time.monotonic()
        with (
            CaptureQueriesContext(connection) as queries,
            transaction.atomic(),
            credentials.current_user_scope(user),
        ):
            try:
                result = ensure_episode_events(
                    user,
                    Sources.TMDB.value,
                    media_id,
                    parsed,
                    conflicts="item",
                    timings=timings,
                )
                outcomes.update(result.outcomes.values())
            except EpisodeEnsureError as err:
                error = err.kind
            # Always undone: the profile must never change the library.
            transaction.set_rollback(True)
        total_ms = int((time.monotonic() - started) * 1000)
        sql_ms = int(sum(float(query["time"]) for query in queries.captured_queries) * 1000)
        stages = " ".join(f"{key}={value}" for key, value in timings.items())
        summary = " ".join(f"{key}={value}" for key, value in sorted(outcomes.items()))
        self.stdout.write(
            f"show {media_id}: events={len(parsed)} total_ms={total_ms} sql_ms={sql_ms} "
            f"queries={len(queries.captured_queries)} {stages} {summary}"
            + (f" error={error}" if error else ""),
        )
