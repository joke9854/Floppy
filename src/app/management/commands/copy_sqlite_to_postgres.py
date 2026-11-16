"""Copy the SQLite database into an empty Postgres database (run at start)."""

import sys
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from config import sqlite_to_postgres

# Exit status of --needed when no copy is due (0 means one is).
NOT_NEEDED = 3


class Command(BaseCommand):
    """Copy an existing SQLite install into Postgres once, keeping the file."""

    help = (
        "Copy db.sqlite3 into the configured Postgres database when Postgres "
        "has no accounts yet. The SQLite file is read-only here and kept."
    )

    def add_arguments(self, parser):
        """Register the command's arguments."""
        parser.add_argument(
            "--needed",
            action="store_true",
            help=f"Change nothing; exit 0 when a copy is due, {NOT_NEEDED} when not.",
        )

    def handle(self, *args, **options):
        """Copy, or report why no copy is due."""
        sqlite_path = Path(settings.FLOPPY_DB_PATH)
        reason = sqlite_to_postgres.skip_reason(sqlite_path)
        if options["needed"]:
            if reason:
                self.stdout.write(f"No SQLite copy needed: {reason}")
                sys.exit(NOT_NEEDED)
            self.stdout.write("The SQLite database will be copied to Postgres")
            return
        if reason:
            self.stdout.write(f"Skipping the SQLite copy: {reason}")
            return

        self.stdout.write("Copying the SQLite database to Postgres")
        try:
            counts = sqlite_to_postgres.copy_database(
                sqlite_path, log=self.stdout.write
            )
        except sqlite_to_postgres.CopyError as error:
            raise CommandError(str(error)) from error
        except DatabaseError as error:
            msg = f"Postgres rejected the copy; nothing was copied: {error}"
            raise CommandError(msg) from error
        self.stdout.write(
            self.style.SUCCESS(
                f"Copied {sum(counts.values())} rows in {len(counts)} tables. "
                f"The SQLite file is kept at {sqlite_path}."
            )
        )
