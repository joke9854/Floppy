"""v2 P2-A: copying an existing SQLite install into Postgres.

The value checks run everywhere. The full copy needs Postgres: CI runs it in
the "SQLite to Postgres copy" job against a Postgres service; elsewhere it is
skipped.
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import skipUnless

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, TransactionTestCase

from config import sqlite_to_postgres
from config.sqlite_to_postgres import Column, CopyError, convert_value


class ConvertValueTests(SimpleTestCase):
    def test_sqlite_values_become_postgres_values(self):
        cases = [
            (1, Column("a", "boolean"), True),
            (0, Column("a", "boolean"), False),
            ("12", Column("a", "integer"), 12),
            (5_000_000, Column("a", "interval"), timedelta(seconds=5)),
            ('{"a": 1}', Column("a", "jsonb"), '{"a": 1}'),
            (3, Column("a", "jsonb"), "3"),
            (42, Column("a", "character varying", 10), "42"),
            (memoryview(b"xy"), Column("a", "bytea"), b"xy"),
            (
                "2026-11-16 08:15:30.123456",
                Column("a", "timestamp with time zone"),
                "2026-11-16 08:15:30.123456",
            ),
            (None, Column("a", "boolean"), None),
        ]
        for value, column, expected in cases:
            with self.subTest(value=value, data_type=column.data_type):
                self.assertEqual(convert_value(value, column), expected)

    def test_values_postgres_rejects_are_reported(self):
        for value, column in (
            ("x" * 21, Column("source", "character varying", 20)),
            ("a\x00b", Column("title", "text")),
            (2**31, Column("n", "integer")),
            ("seven", Column("n", "bigint")),
            ("maybe", Column("flag", "boolean")),
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                convert_value(value, column)


class SkipReasonTests(TestCase):
    def test_sqlite_installs_never_copy(self):
        if connection.vendor == "postgresql":
            self.skipTest("runs on SQLite")
        self.assertIn(
            "not configured for Postgres", sqlite_to_postgres.skip_reason("x")
        )
        with self.assertRaises(SystemExit) as raised:
            call_command("copy_sqlite_to_postgres", "--needed")
        self.assertEqual(raised.exception.code, 3)


def _sqlite_env(db_path):
    env = dict(os.environ)
    env["DB_HOST"] = ""
    env["FLOPPY_DB_PATH"] = str(db_path)
    return env


def _run_on_sqlite(db_path, *args):
    subprocess.run(  # noqa: S603 - fixed manage.py arguments
        [sys.executable, "manage.py", *args],
        cwd=settings.BASE_DIR,
        env=_sqlite_env(db_path),
        check=True,
        capture_output=True,
        timeout=900,
    )


FIXTURE = """
import events.tasks  # noqa: F401
from datetime import datetime, UTC
from unittest.mock import patch
# Save signals queue Celery tasks; the fixture needs no broker.
patch("celery.app.task.Task.apply_async").start()
from app.models import Item, MediaTypes, Movie, Sources, Status
from users.models import User
user = User.objects.create_user(username="copied", password="x-unused-123")
user.plex_webhook_libraries = ["m1::1"]
user.save()
item = Item.objects.create(
    media_id="701", source=Sources.TMDB.value, media_type=MediaTypes.MOVIE.value,
    title="Copied movie", image="https://example.com/p.jpg",
)
Movie.objects.create(
    item=item, user=user, status=Status.COMPLETED.value,
    end_date=datetime(2026, 11, 16, 8, 15, 30, 123456, tzinfo=UTC),
)
"""


@skipUnless(connection.vendor == "postgresql", "needs Postgres (CI copy job)")
class CopyToPostgresTests(TransactionTestCase):
    """Builds a real SQLite install with migrate, then copies it."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.workdir = Path(tempfile.mkdtemp())
        cls.template = cls.workdir / "template.sqlite3"
        _run_on_sqlite(cls.template, "migrate", "--noinput")
        _run_on_sqlite(cls.template, "shell", "-c", FIXTURE)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workdir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.db_path = self.workdir / f"{self._testMethodName}.sqlite3"
        shutil.copyfile(self.template, self.db_path)

    def test_copy_keeps_every_row_and_the_exact_watch_time(self):
        from app.models import Movie
        from users.models import User

        self.assertIsNone(sqlite_to_postgres.skip_reason(self.db_path))
        counts = sqlite_to_postgres.copy_database(self.db_path, log=lambda _m: None)

        source = sqlite3.connect(self.db_path)
        for table, count in counts.items():
            expected = sqlite_to_postgres._sqlite_count(source, table)
            self.assertEqual(count, expected, table)
        source.close()

        user = User.objects.get(username="copied")
        self.assertEqual(user.plex_webhook_libraries, ["m1::1"])
        self.assertTrue(user.is_active)
        movie = Movie.objects.get(user=user)
        self.assertEqual(
            movie.end_date, datetime(2026, 11, 16, 8, 15, 30, 123456, tzinfo=UTC)
        )
        # Sequences continue after the copied ids.
        self.assertGreater(User.objects.create_user(username="after").id, user.id)
        self.assertTrue(sqlite_to_postgres.marker_path(self.db_path).exists())
        self.assertIn("already copied", sqlite_to_postgres.skip_reason(self.db_path))

    def test_a_bad_value_copies_nothing(self):
        from users.models import User

        source = sqlite3.connect(self.db_path)
        source.execute("UPDATE app_item SET source = ?", ("x" * 40,))
        source.commit()
        source.close()

        with self.assertRaisesMessage(CopyError, "app_item.source"):
            sqlite_to_postgres.copy_database(self.db_path, log=lambda _m: None)
        self.assertFalse(User.objects.exists())
        self.assertFalse(sqlite_to_postgres.marker_path(self.db_path).exists())

    def test_postgres_with_accounts_is_never_overwritten(self):
        from users.models import User

        User.objects.create_user(username="already-here")
        self.assertIn(
            "already has accounts", sqlite_to_postgres.skip_reason(self.db_path)
        )
        with self.assertRaises(CopyError):
            sqlite_to_postgres.copy_database(self.db_path, log=lambda _m: None)
        self.assertEqual(
            list(User.objects.values_list("username", flat=True)), ["already-here"]
        )
