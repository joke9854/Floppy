"""Copy an existing SQLite install into an empty Postgres database (v2 P2-A).

Postgres is the default database from v2 on. An install that starts with
``DB_HOST`` set, a Postgres database without accounts and a ``db.sqlite3``
that has accounts is copied over once, at start, by the entrypoint:

1. ``copy_sqlite_to_postgres --needed`` decides whether a copy is due.
2. The SQLite file is migrated to the current code (``DB_HOST=`` migrate),
   the same step a normal SQLite start runs.
3. Postgres is migrated as usual, so both sides have the same tables.
4. ``copy_sqlite_to_postgres`` copies every table in one transaction, checks
   the row count of each and resets the sequences. Anything wrong rolls the
   whole copy back and the container stops, so Floppy never serves an empty
   Postgres in place of the user's data; the next start tries again.

The SQLite file is only ever opened read-only here and is never deleted. A
marker file next to it records the finished copy.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.utils import timezone

MARKER_SUFFIX = ".migrated-to-postgres"
# Postgres keeps its own record from its own migrate run.
SKIPPED_TABLES = frozenset({"django_migrations"})
INTEGER_RANGES = {
    "smallint": (-(2**15), 2**15 - 1),
    "integer": (-(2**31), 2**31 - 1),
    "bigint": (-(2**63), 2**63 - 1),
}
# Row ids kept per problem in the report: enough to find the rows, not a dump.
PROBLEM_SAMPLE = 5


class CopyError(Exception):
    """The copy cannot run or did not verify; Postgres was left unchanged."""


@dataclass(frozen=True)
class Column:
    """A Postgres column the copy writes."""

    name: str
    data_type: str
    max_length: int | None = None


class _Problem:
    """Value Postgres would reject: counted per table, column and kind."""

    def __init__(self):
        self.counts = defaultdict(int)
        self.samples = defaultdict(list)

    def add(self, table, column, kind, row_id):
        key = (table, column, kind)
        self.counts[key] += 1
        if row_id is not None and len(self.samples[key]) < PROBLEM_SAMPLE:
            self.samples[key].append(row_id)

    def __bool__(self):
        return bool(self.counts)

    def report(self):
        lines = []
        for (table, column, kind), count in sorted(self.counts.items()):
            ids = ", ".join(str(i) for i in self.samples[(table, column, kind)])
            suffix = f" (ids {ids})" if ids else ""
            lines.append(f"  {table}.{column}: {count} row(s) {kind}{suffix}")
        return "\n".join(lines)


def marker_path(sqlite_path):
    """Return the file that records a finished copy next to the SQLite file."""
    return Path(f"{sqlite_path}{MARKER_SUFFIX}")


def _quote(name):
    return connection.ops.quote_name(name)


# Table and column names below come from the databases' own catalogs
# (sqlite_master, information_schema), never from a request, and are quoted.


def _sqlite_count(source, table):
    return source.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]  # noqa: S608


def _postgres_count(cursor, table):
    cursor.execute(f"SELECT count(*) FROM {_quote(table)}")  # noqa: S608
    return cursor.fetchone()[0]


def _open_source(sqlite_path):
    return sqlite3.connect(f"file:{Path(sqlite_path).as_posix()}?mode=ro", uri=True)


def _sqlite_tables(source):
    return {
        row[0]
        for row in source.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not row[0].startswith("sqlite_")
    }


def _sqlite_user_count(source):
    table = get_user_model()._meta.db_table
    if table not in _sqlite_tables(source):
        return 0
    return _sqlite_count(source, table)


def _postgres_user_count():
    table = get_user_model()._meta.db_table
    if table not in connection.introspection.table_names():
        return 0
    with connection.cursor() as cursor:
        return _postgres_count(cursor, table)


def skip_reason(sqlite_path):
    """Return why no copy is due, or None when one is."""
    if connection.vendor != "postgresql":
        return "Floppy is not configured for Postgres (DB_HOST is not set)"
    sqlite_path = Path(sqlite_path)
    if not sqlite_path.is_file():
        return "there is no SQLite database to copy"
    if marker_path(sqlite_path).exists():
        return "this SQLite database was already copied"
    source = _open_source(sqlite_path)
    try:
        if not _sqlite_user_count(source):
            return "the SQLite database has no accounts"
    finally:
        source.close()
    if _postgres_user_count():
        return "the Postgres database already has accounts"
    return None


def _postgres_columns():
    """Return {table: [Column]} for the writable columns of every base table."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.table_name, c.column_name, c.data_type,
                   c.character_maximum_length
            FROM information_schema.columns c
            JOIN information_schema.tables t
              ON t.table_schema = c.table_schema AND t.table_name = c.table_name
            WHERE c.table_schema = current_schema()
              AND t.table_type = 'BASE TABLE'
              AND c.is_generated = 'NEVER'
            ORDER BY c.table_name, c.ordinal_position
            """
        )
        tables = defaultdict(list)
        for table, name, data_type, max_length in cursor.fetchall():
            if table not in SKIPPED_TABLES:
                tables[table].append(Column(name, data_type, max_length))
    return dict(tables)


def _check_migrations(source):
    with connection.cursor() as cursor:
        cursor.execute("SELECT app, name FROM django_migrations")
        postgres = set(cursor.fetchall())
    sqlite_rows = set(source.execute("SELECT app, name FROM django_migrations"))
    missing = sorted(postgres - sqlite_rows)
    if missing:
        names = ", ".join(f"{app}.{name}" for app, name in missing[:5])
        msg = (
            f"The SQLite database lacks {len(missing)} migration(s) Postgres has "
            f"({names}). Migrate it first: DB_HOST= python manage.py migrate"
        )
        raise CopyError(msg)


def _check_foreign_keys(source):
    broken = defaultdict(int)
    for table, *_ in source.execute("PRAGMA foreign_key_check"):
        broken[table] += 1
    if broken:
        tables = ", ".join(f"{t} ({n})" for t, n in sorted(broken.items()))
        msg = (
            "The SQLite database has rows pointing at missing rows: "
            f"{tables}. Start once without DB_HOST so the SQLite storage "
            "check can repair them, then start on Postgres again."
        )
        raise CopyError(msg)


def convert_value(value, column):
    """Return `value` from SQLite as Postgres takes it, or raise ValueError.

    The ValueError message names the problem kind for the report.
    """
    if value is None:
        return None
    data_type = column.data_type
    if data_type == "boolean":
        if isinstance(value, int):
            return bool(value)
        if isinstance(value, str) and value.lower() in {"0", "1", "true", "false"}:
            return value.lower() in {"1", "true"}
        msg = "are not true/false"
        raise ValueError(msg)
    if data_type in INTEGER_RANGES:
        try:
            number = int(value)
        except (TypeError, ValueError):
            msg = "are not whole numbers"
            raise ValueError(msg) from None
        low, high = INTEGER_RANGES[data_type]
        if not low <= number <= high:
            msg = f"do not fit a Postgres {data_type}"
            raise ValueError(msg)
        return number
    if data_type == "interval":
        # Django stores a DurationField on SQLite as microseconds.
        if isinstance(value, (int, float)):
            return timedelta(microseconds=value)
        return value
    if data_type in {"json", "jsonb"}:
        return value if isinstance(value, str) else json.dumps(value)
    if data_type == "bytea":
        return bytes(value) if isinstance(value, memoryview) else value
    if data_type in {"character varying", "character", "text"}:
        if not isinstance(value, str):
            value = str(value)
        if "\x00" in value:
            msg = "contain a NUL character"
            raise ValueError(msg)
        if column.max_length and len(value) > column.max_length:
            msg = f"are longer than {column.max_length} characters"
            raise ValueError(msg)
        return value
    # Timestamps, dates and times stay text: SQLite holds Django's UTC text
    # and the copy session runs in UTC, so Postgres parses the exact instant.
    return value


def _copy_table(source, cursor, table, columns, problems):
    source_columns = {row[1] for row in source.execute(f'PRAGMA table_info("{table}")')}
    missing = [c.name for c in columns if c.name not in source_columns]
    if missing:
        msg = f"SQLite table {table} has no column(s) {', '.join(missing)}"
        raise CopyError(msg)
    names = [c.name for c in columns]
    id_index = names.index("id") if "id" in names else None
    select = "SELECT " + ", ".join(f'"{n}"' for n in names) + f' FROM "{table}"'  # noqa: S608
    copy_sql = (
        f"COPY {_quote(table)} ({', '.join(_quote(n) for n in names)}) FROM STDIN"
    )
    copied = 0
    # Django's cursor wraps psycopg's; COPY needs the psycopg one.
    with cursor.cursor.copy(copy_sql) as copy:
        for row in source.execute(select):
            converted = []
            row_ok = True
            for value, column in zip(row, columns, strict=True):
                try:
                    converted.append(convert_value(value, column))
                except ValueError as error:
                    row_id = row[id_index] if id_index is not None else None
                    problems.add(table, column.name, str(error), row_id)
                    row_ok = False
            if row_ok:
                copy.write_row(converted)
                copied += 1
    return copied


def _reset_sequences(cursor):
    cursor.execute(
        """
        SELECT table_name, column_name FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND (is_identity = 'YES' OR column_default LIKE 'nextval(%%')
        """
    )
    for table, column in cursor.fetchall():
        cursor.execute(
            f"SELECT setval(pg_get_serial_sequence(%s, %s), "  # noqa: S608
            f"COALESCE(MAX({_quote(column)}), 1), MAX({_quote(column)}) IS NOT NULL) "
            f"FROM {_quote(table)}",
            [_quote(table), column],
        )


def copy_database(sqlite_path, log=print):
    """Copy every table of the SQLite file into Postgres; return row counts.

    Raises CopyError when the copy cannot run or does not verify. The copy is
    one transaction, so on any error Postgres keeps no copied rows.
    """
    source = _open_source(sqlite_path)
    try:
        _check_migrations(source)
        _check_foreign_keys(source)
        tables = _postgres_columns()
        source_tables = _sqlite_tables(source)
        missing = sorted(set(tables) - source_tables)
        if missing:
            msg = f"SQLite has no table(s) {', '.join(missing)}"
            raise CopyError(msg)
        for leftover in sorted(source_tables - set(tables) - SKIPPED_TABLES):
            rows = _sqlite_count(source, leftover)
            log(
                f"Not copied: SQLite table {leftover} ({rows} rows) no longer exists in Floppy"
            )

        problems = _Problem()
        counts = {}
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("SET LOCAL TIME ZONE 'UTC'")
            if _postgres_user_count():
                msg = "The Postgres database already has accounts; nothing was copied"
                raise CopyError(msg)
            # Migrate seeded content types, permissions and schedules with ids
            # of its own; the SQLite rows replace them so references still match.
            cursor.execute(
                "TRUNCATE "
                + ", ".join(_quote(t) for t in sorted(tables))
                + " RESTART IDENTITY CASCADE"
            )
            for table in sorted(tables):
                counts[table] = _copy_table(
                    source, cursor, table, tables[table], problems
                )
                if counts[table]:
                    log(f"Copied {table}: {counts[table]} rows")
            if problems:
                msg = (
                    "Some SQLite values do not fit Postgres; nothing was copied. "
                    "Fix these rows and start again:\n" + problems.report()
                )
                raise CopyError(msg)
            for table in sorted(tables):
                expected = _sqlite_count(source, table)
                actual = _postgres_count(cursor, table)
                if actual != expected or counts[table] != expected:
                    msg = (
                        f"Row count mismatch in {table}: SQLite {expected}, "
                        f"Postgres {actual}; nothing was copied"
                    )
                    raise CopyError(msg)
            _reset_sequences(cursor)
            try:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            except Exception as error:
                msg = f"Postgres rejected a reference after the copy: {error}"
                raise CopyError(msg) from error
    finally:
        source.close()

    marker_path(sqlite_path).write_text(
        json.dumps(
            {
                "copied_at": timezone.now().isoformat(),
                "tables": len(counts),
                "rows": sum(counts.values()),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return counts
