"""Write a verified raw copy of the live SQLite database to a directory."""

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.sqlite_integrity import create_live_database_snapshot

SNAPSHOT_TIMEOUT_SECONDS = 300


class Command(BaseCommand):
    """Take a consistent snapshot of the SQLite database, read-only on the source."""

    help = (
        "Write a verified SQLite snapshot of the live database into --dest. "
        "The source is only read. Only the newest snapshot in --dest is kept, "
        "so use a dedicated directory."
    )

    def add_arguments(self, parser):
        """Declare the destination directory."""
        parser.add_argument(
            "--dest",
            required=True,
            help="Dedicated directory to write the snapshot into.",
        )

    def handle(self, *args, **options):
        """Write the snapshot and print its path."""
        if not settings.USING_SQLITE_DATABASE:
            message = (
                "This database is not SQLite. Use pg_dump to copy a PostgreSQL "
                "database."
            )
            raise CommandError(message)

        path = create_live_database_snapshot(
            str(settings.FLOPPY_DB_PATH),
            Path(options["dest"]),
            max_keep=1,
            timeout_seconds=SNAPSHOT_TIMEOUT_SECONDS,
        )
        if path is None:
            message = "The snapshot could not be written. See the log for the reason."
            raise CommandError(message)

        self.stdout.write(str(path))
