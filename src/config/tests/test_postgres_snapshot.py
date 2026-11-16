"""Nightly pg_dump snapshot for Postgres installs (v2 P2-A)."""

import shutil
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock, skipUnless

from django.db import connection
from django.test import SimpleTestCase, TestCase

from config import postgres_snapshot


class FakeRun:
    """Stands in for subprocess.run: pg_dump writes a file, pg_restore lists it."""

    def __init__(self, dump_code=0, listing="1; TABLE DATA public users_user\n"):
        """Choose pg_dump's exit code and what pg_restore lists."""
        self.dump_code = dump_code
        self.listing = listing
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args[0].endswith("pg_dump"):
            target = next(a for a in args if a.startswith("--file="))[len("--file=") :]
            Path(target).write_bytes(b"PGDMP")
            return subprocess.CompletedProcess(args, self.dump_code, "", "dump error")
        return subprocess.CompletedProcess(args, 0, self.listing, "")


class SnapshotTests(SimpleTestCase):
    def setUp(self):
        self.dest = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dest, ignore_errors=True)
        patcher = mock.patch.object(
            postgres_snapshot.shutil,
            "which",
            side_effect=lambda name: f"/usr/bin/{name}",
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _snapshot(self, run, max_keep=3):
        databases = {
            "default": {
                "HOST": "db",
                "PORT": "5432",
                "USER": "floppy",
                "NAME": "floppy",
                "PASSWORD": "s3cret-value",
            }
        }
        with (
            mock.patch.object(postgres_snapshot.subprocess, "run", run),
            mock.patch.object(
                postgres_snapshot, "settings", SimpleNamespace(DATABASES=databases)
            ),
        ):
            return postgres_snapshot.create_postgres_snapshot(
                self.dest, max_keep=max_keep
            )

    def test_writes_a_verified_dump_and_keeps_the_password_off_the_command_line(self):
        run = FakeRun()
        path = self._snapshot(run)
        self.assertTrue(path.name.startswith("floppy-postgres-"))
        self.assertTrue(path.exists())
        self.assertEqual(list(self.dest.glob(".*.tmp")), [])
        args, kwargs = run.calls[0]
        self.assertNotIn("s3cret-value", " ".join(args))
        self.assertEqual(kwargs["env"]["PGPASSWORD"], "s3cret-value")

    def test_a_failed_dump_leaves_nothing_behind(self):
        self.assertIsNone(self._snapshot(FakeRun(dump_code=1)))
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_an_unverified_dump_is_discarded(self):
        self.assertIsNone(self._snapshot(FakeRun(listing="")))
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_only_the_newest_are_kept(self):
        for stamp in ("20260101T000000Z", "20260102T000000Z", "20260103T000000Z"):
            (self.dest / f"floppy-postgres-{stamp}-aaaa.dump").write_bytes(b"old")
        path = self._snapshot(FakeRun(), max_keep=2)
        kept = sorted(p.name for p in self.dest.glob("floppy-postgres-*.dump"))
        self.assertEqual(len(kept), 2)
        self.assertIn(path.name, kept)
        self.assertIn("floppy-postgres-20260103T000000Z-aaaa.dump", kept)

    def test_missing_pg_dump_is_an_error_not_a_crash(self):
        with mock.patch.object(postgres_snapshot.shutil, "which", return_value=None):
            self.assertIsNone(
                postgres_snapshot.create_postgres_snapshot(self.dest, max_keep=1)
            )


@skipUnless(
    connection.vendor == "postgresql" and shutil.which("pg_dump"),
    "needs Postgres and pg_dump (CI copy job)",
)
class RealPgDumpTests(TestCase):
    def test_real_dump_verifies(self):
        dest = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, dest, ignore_errors=True)
        # Django points settings.DATABASES at the test database already.
        path = postgres_snapshot.create_postgres_snapshot(dest, max_keep=1)
        self.assertIsNotNone(path)
        self.assertGreater(path.stat().st_size, 0)
