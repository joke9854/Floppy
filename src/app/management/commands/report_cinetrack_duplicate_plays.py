"""Report plays that look like the same viewing recorded twice.

CineTrack's bootstrap adopts an existing play only when its watched time is
the exact same instant. A play written earlier with a different time (the
server's receive time, a date-only import, a timezone-shifted import) is kept
and the bootstrap adds its own play next to it. This command lists those
suspicious pairs so they can be reviewed before anything is changed.

Strictly read-only: it never writes, and it has no option to.

Categories, checked in this order for every pair of plays of one item:
- near: within `duplicate_play_window` for the item's runtime, the same rule
  Floppy uses everywhere else to call two plays one viewing;
- tz_offset: apart by an exact whole number of hours (1-14), the signature of
  one source storing local time as UTC;
- date_only: one play is exactly midnight UTC and the other is on that date.
A genuine rewatch can still land in tz_offset or date_only, so those are
listed for review, not presumed duplicates.
"""

from collections import defaultdict
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from app.fork_services_play_dedupe import duplicate_play_window
from app.models import Episode, Movie, MoviePlay

CATEGORIES = ("near", "tz_offset", "date_only")
MAX_TZ_OFFSET_HOURS = 14


def classify_pair(first, second, runtime_minutes):
    """Return the category for two play times of one item, or None."""
    earlier, later = sorted((first, second))
    gap = later - earlier
    if gap < duplicate_play_window(runtime_minutes):
        return "near"
    if gap <= timedelta(hours=MAX_TZ_OFFSET_HOURS) and gap % timedelta(
        hours=1
    ) == timedelta(0):
        return "tz_offset"
    for midnight, other in ((earlier, later), (later, earlier)):
        if (
            midnight.timetz().replace(tzinfo=None) == time(0)
            and midnight.date() == other.date()
        ):
            return "date_only"
    return None


class Command(BaseCommand):
    """List suspected duplicate movie/episode plays (read-only)."""

    help = (
        "Read-only report of movie/episode plays that look like one viewing "
        "recorded twice (near in time, whole-hour offset, or date-only)"
    )

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--username",
            type=str,
            default=None,
            help="Only report entries belonging to this user",
        )
        parser.add_argument(
            "--samples",
            type=int,
            default=20,
            help="Example items to print per category (default 20)",
        )

    def handle(self, *_args, **options):
        """Execute the command."""
        self.samples = max(options["samples"], 0)
        users = get_user_model().objects.all()
        if options["username"]:
            users = users.filter(username=options["username"])
        users = list(users.order_by("username"))
        if not users:
            self.stdout.write("No matching users.")
            return

        self.stdout.write("READ-ONLY REPORT (nothing is changed)\n")
        for user in users:
            self._report(user, "Episodes", self._episode_groups(user))
            self._report(user, "Movies", self._movie_groups(user))

    def _episode_groups(self, user):
        """Yield (label, runtime, [(end_date, origin)]) per watched episode."""
        groups = defaultdict(list)
        labels = {}
        runtimes = {}
        episodes = (
            Episode.objects.filter(related_season__user=user, end_date__isnull=False)
            .select_related("item")
            .only(
                "end_date",
                "watch_operation_id",
                "item__source",
                "item__media_id",
                "item__title",
                "item__season_number",
                "item__episode_number",
                "item__runtime_minutes",
            )
        )
        for episode in episodes.iterator(chunk_size=2000):
            item = episode.item
            key = (item.source, item.media_id, item.season_number, item.episode_number)
            origin = "cinetrack" if episode.watch_operation_id else "other"
            groups[key].append((episode.end_date, origin))
            labels[key] = (
                f"{item.title} S{item.season_number or 0:02d}E{item.episode_number or 0:02d}"
            )
            runtimes[key] = item.runtime_minutes
        for key, plays in groups.items():
            yield labels[key], runtimes[key], plays

    def _movie_groups(self, user):
        """Yield (label, runtime, [(end_date, origin)]) per watched movie.

        Reads both storage shapes: MoviePlay rows, and importer-created extra
        Movie rows whose end_date is the play.
        """
        groups = defaultdict(list)
        labels = {}
        runtimes = {}
        movies = Movie.objects.filter(user=user).select_related("item")
        with_plays = set(
            MoviePlay.objects.filter(movie__user=user)
            .values_list("movie_id", flat=True)
            .distinct(),
        )
        plays_by_movie = defaultdict(list)
        for play in MoviePlay.objects.filter(
            movie__user=user, end_date__isnull=False
        ).only(
            "movie_id",
            "end_date",
            "external_id",
        ):
            origin = (
                "cinetrack"
                if (play.external_id or "").startswith("cinetrack:")
                else "other"
            )
            plays_by_movie[play.movie_id].append((play.end_date, origin))
        for movie in movies.iterator(chunk_size=2000):
            item = movie.item
            key = (item.source, item.media_id)
            labels[key] = item.title
            runtimes[key] = item.runtime_minutes
            if movie.id in with_plays:
                groups[key].extend(plays_by_movie.get(movie.id, []))
            elif movie.end_date is not None:
                groups[key].append((movie.end_date, "other"))
        for key, plays in groups.items():
            yield labels[key], runtimes[key], plays

    def _report(self, user, kind, groups):
        """Print counts and examples for one user and media kind."""
        counts = dict.fromkeys(CATEGORIES, 0)
        examples = defaultdict(list)
        checked = 0
        for label, runtime, plays in groups:
            if len(plays) < 2:  # noqa: PLR2004
                continue
            checked += 1
            ordered = sorted(plays)
            found = {}
            for i, (first, first_origin) in enumerate(ordered):
                for second, second_origin in ordered[i + 1 :]:
                    category = classify_pair(first, second, runtime)
                    if category and category not in found:
                        found[category] = (
                            f"{label}: {first.isoformat()} [{first_origin}] / "
                            f"{second.isoformat()} [{second_origin}]"
                        )
            for category, example in found.items():
                counts[category] += 1
                if len(examples[category]) < self.samples:
                    examples[category].append(example)

        self.stdout.write(
            f"\n{user.username} - {kind}: {checked} item(s) with 2+ plays; "
            + ", ".join(f"{category}={counts[category]}" for category in CATEGORIES),
        )
        for category in CATEGORIES:
            for example in examples[category]:
                self.stdout.write(f"  [{category}] {example}")
