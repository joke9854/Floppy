"""Move CineTrack episode plays stored one episode off in absolutely numbered seasons.

Some TMDB shows keep absolute episode numbers inside their seasons (One Piece
S06 lists 144-195, Naruto Shippuden S20 lists 459-...). Before CineTrack-API
matched those by number, an episode whose TMDB and TVDB air dates disagree
could be matched by air date to its neighbour: Naruto Shippuden 459 was stored
on S20E460, leaving 460 with two plays and 459 with none.

That leaves a recognisable shape, and only that shape is touched: in a season
whose numbering does not restart at 1, an episode holding two or more plays
written by CineTrack (they carry a watch operation id) next to an episode TMDB
lists that has no play at all. The earliest play moves to an empty previous
episode, or the latest to an empty next one; when both neighbours are empty
the case is only reported. Moved plays keep their exact time and operation id.

Dry run by default. A real rewatch next to a skipped episode has the same
shape, so review the list before passing --apply.
"""

from collections import defaultdict

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from app.fork_services_episode import create_episode_watch
from app.models import Episode, Season, Sources
from app.providers import services


def season_episode_numbers(season):
    """(numbers TMDB lists for the season, its metadata), or (set(), None)."""
    media_id = season.item.media_id
    number = season.item.season_number
    metadata = services.get_media_metadata("tv_with_seasons", media_id, Sources.TMDB.value, [number])
    season_metadata = metadata.get(f"season/{number}") if isinstance(metadata, dict) else None
    if not isinstance(season_metadata, dict):
        return set(), None
    numbers = {
        int(row["episode_number"])
        for row in season_metadata.get("episodes") or []
        if isinstance(row, dict) and row.get("episode_number") is not None
    }
    return numbers, season_metadata


def misplaced_plays(season, numbers):
    """Yield (play, target episode number, note) for one absolutely numbered season."""
    plays = defaultdict(list)
    for play in (
        Episode.objects.filter(related_season=season)
        .select_related("item")
        .order_by("end_date", "id")
    ):
        plays[play.item.episode_number].append(play)
    for episode_number in sorted(plays):
        ours = [play for play in plays[episode_number] if play.watch_operation_id]
        if len(ours) < 2:  # noqa: PLR2004
            continue
        previous, following = episode_number - 1, episode_number + 1
        previous_empty = previous in numbers and not plays.get(previous)
        following_empty = following in numbers and not plays.get(following)
        if previous_empty and following_empty:
            yield None, None, f"E{episode_number}: both neighbours empty, review by hand"
        elif previous_empty:
            yield ours[0], previous, None
        elif following_empty:
            yield ours[-1], following, None


class Command(BaseCommand):
    """Relocate CineTrack plays one episode off in absolutely numbered seasons."""

    help = (
        "Move CineTrack episode plays stored on a neighbouring episode in "
        "absolutely numbered TMDB seasons (dry run unless --apply)"
    )

    def add_arguments(self, parser):
        """Add command line arguments."""
        parser.add_argument("--apply", action="store_true", help="Move the plays (default is a dry run)")
        parser.add_argument("--username", type=str, default=None, help="Only process this user")

    def handle(self, *_args, **options):
        """Execute the command."""
        users = get_user_model().objects.all()
        if options["username"]:
            users = users.filter(username=options["username"])
        apply = options["apply"]
        self.stdout.write("APPLYING" if apply else "DRY RUN (nothing is changed)")
        total = 0
        for user in users.order_by("username"):
            seasons = (
                Season.objects.filter(
                    user=user,
                    item__source=Sources.TMDB.value,
                    item__season_number__gte=2,
                    episodes__watch_operation_id__isnull=False,
                )
                .select_related("item", "related_tv__item")
                .distinct()
                .order_by("item__media_id", "item__season_number")
            )
            for season in seasons:
                numbers, season_metadata = season_episode_numbers(season)
                # Only seasons that keep absolute numbers (do not restart at 1).
                if not numbers or min(numbers) <= 1:
                    continue
                label = f"{user.username} {season.related_tv.item.title} (TMDB {season.item.media_id}) S{season.item.season_number:02d}"
                for play, target, note in misplaced_plays(season, numbers):
                    if note:
                        self.stdout.write(f"  {label} {note}")
                        continue
                    total += 1
                    self.stdout.write(
                        f"  {label}: play #{play.pk} at {play.end_date.isoformat()} "
                        f"E{play.item.episode_number} -> E{target}",
                    )
                    if apply:
                        self._move(season, play, target, season_metadata)
        verb = "moved" if apply else "would be moved"
        self.stdout.write(f"\nPlays {verb}: {total}")
        if not apply and total:
            self.stdout.write(self.style.WARNING("Review the list, then re-run with --apply."))

    @staticmethod
    def _move(season, play, target, season_metadata):
        operation_id = play.watch_operation_id
        end_date = play.end_date
        with transaction.atomic():
            target_item = season.get_episode_item(target, season_metadata=season_metadata)
            # The operation id is unique, so the old row goes first.
            play.delete()
            create_episode_watch(season, target_item, end_date, watch_operation_id=operation_id)
