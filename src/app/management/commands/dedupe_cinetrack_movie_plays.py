"""Remove movie plays CineTrack recorded twice at the exact same instant.

Before CineTrack-API b281d630, the movie bootstrap endpoint only recognised an
existing exact-instant play when it had no external id. Reconnecting CineTrack
(which starts a new connection id) therefore added a second play next to every
play the first connection had already written.

Only that exact shape is removed: two or more plays of the same movie with the
identical end_date where the extra plays carry a CineTrack external id. The
oldest play of each group is kept. Plays at different instants (rewatches),
plays from other sources, and episodes are never touched.

Dry run by default. Pass --apply to delete.
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import MoviePlay

CINETRACK_PREFIX = "cinetrack:"


def cinetrack_duplicate_plays(user):
    """Return [(keeper, [duplicates])] for one user's exact-instant movie plays."""
    groups = defaultdict(list)
    plays = (
        MoviePlay.objects.filter(movie__user=user, end_date__isnull=False)
        .select_related("movie__item")
        .order_by("id")
    )
    for play in plays:
        groups[(play.movie_id, play.end_date)].append(play)

    found = []
    for group in groups.values():
        if len(group) < 2:  # noqa: PLR2004
            continue
        keeper, *rest = group
        duplicates = [
            play
            for play in rest
            if (play.external_id or "").startswith(CINETRACK_PREFIX)
        ]
        if duplicates:
            found.append((keeper, duplicates))
    return found


class Command(BaseCommand):
    """Collapse exact-instant duplicate movie plays written by CineTrack."""

    help = (
        "Remove movie plays CineTrack recorded twice at the exact same instant "
        "(dry run unless --apply)"
    )

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Delete the duplicates (default is a dry run)",
        )
        parser.add_argument(
            "--username", type=str, default=None, help="Only process this user"
        )
        parser.add_argument(
            "--samples",
            type=int,
            default=20,
            help="Example movies to print (default 20)",
        )

    def handle(self, *_args, **options):
        """Execute the command."""
        users = get_user_model().objects.all()
        if options["username"]:
            users = users.filter(username=options["username"])
        users = list(users.order_by("username"))
        if not users:
            self.stdout.write("No matching users.")
            return

        apply = options["apply"]
        self.stdout.write("APPLYING" if apply else "DRY RUN (nothing is changed)")
        total = 0
        for user in users:
            found = cinetrack_duplicate_plays(user)
            count = sum(len(duplicates) for _, duplicates in found)
            total += count
            self.stdout.write(
                f"\n{user.username}: {len(found)} movie(s), {count} duplicate play(s)"
            )
            for keeper, duplicates in found[: max(options["samples"], 0)]:
                removed = ", ".join(f"#{play.pk}" for play in duplicates)
                self.stdout.write(
                    f"  {keeper.movie.item.title} @ {keeper.end_date.isoformat()}: "
                    f"keep #{keeper.pk}, remove {removed}",
                )
            if apply and count:
                with transaction.atomic():
                    MoviePlay.objects.filter(
                        pk__in=[
                            play.pk for _, duplicates in found for play in duplicates
                        ],
                    ).delete()

        verb = "removed" if apply else "would be removed"
        self.stdout.write(f"\nDuplicate plays {verb}: {total}")
        if not apply and total:
            self.stdout.write(self.style.WARNING("Re-run with --apply to delete them."))
