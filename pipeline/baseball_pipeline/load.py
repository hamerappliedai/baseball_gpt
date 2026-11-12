"""Load a verified release into the `raw` schema.

Raw is a faithful copy of the CSVs: every column is text and names are only
lowercased. Typing, renaming and cleaning happen later, in staging (dbt), so a
bad cast can never lose data on the way in. The only changes made here:
  - the UTF-8 byte-order mark is stripped (it would otherwise end up in the
    first column's name);
  - empty fields become NULL, not empty strings.

The whole load runs in one transaction: readers see the previous release
until the new one commits, and a failure leaves the old tables untouched.

Staging views (dbt) depend on these tables, so a table whose columns are
unchanged is emptied with TRUNCATE and refilled, which keeps those views
working. Only a table whose columns changed is dropped and recreated; that
drops its dependent views too, and `make transform` rebuilds them.
"""

from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from . import config
from .fetch import release_dir, verify
from .manifest import BOM, FileEntry, Manifest

log = logging.getLogger(__name__)

LOAD_LOG = "_load_log"
COPY_CHUNK = 1 << 20


class LoadError(Exception):
    pass


def raw_columns(entry: FileEntry) -> list[str]:
    cols = [c.strip().lower() for c in entry.columns]
    if any(not c for c in cols):
        raise LoadError(f"{entry.name}: blank column name in header")
    if len(cols) != len(set(cols)):
        raise LoadError(f"{entry.name}: columns collide when lowercased: {entry.columns}")
    return cols


def _load_table(cur: psycopg.Cursor, release: str, entry: FileEntry) -> int:
    schema = config.RAW_SCHEMA
    table = sql.Identifier(schema, entry.table)
    cols = raw_columns(entry)
    col_ids = sql.SQL(", ").join(sql.Identifier(c) for c in cols)

    existing = _existing_columns(cur, schema, entry.table)
    if existing == cols:
        cur.execute(sql.SQL("TRUNCATE {}").format(table))
    else:
        if existing is not None:
            log.warning("raw.%s columns changed; recreating it (dependent views are dropped "
                        "and rebuilt by `make transform`)", entry.table)
            cur.execute(sql.SQL("DROP TABLE {} CASCADE").format(table))
        cur.execute(
            sql.SQL("CREATE TABLE {} ({})").format(
                table, sql.SQL(", ").join(sql.SQL("{} text").format(sql.Identifier(c)) for c in cols)
            )
        )

    data = (release_dir(release) / entry.name).read_bytes()
    if data.startswith(BOM):
        data = data[len(BOM) :]

    # FORMAT csv already reads unquoted empty fields as NULL; FORCE_NULL also
    # turns quoted empty strings ("") into NULL.
    copy = sql.SQL(
        "COPY {} ({}) FROM STDIN (FORMAT csv, HEADER true, ENCODING 'UTF8', FORCE_NULL ({}))"
    ).format(table, col_ids, col_ids)
    with cur.copy(copy) as cp:
        for i in range(0, len(data), COPY_CHUNK):
            cp.write(data[i : i + COPY_CHUNK])

    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(table))
    (rows,) = cur.fetchone()
    if rows != entry.rows:
        raise LoadError(f"{entry.table}: loaded {rows} rows, manifest says {entry.rows}")

    cur.execute(
        sql.SQL("COMMENT ON TABLE {} IS {}").format(
            table,
            sql.Literal(f"Lahman {release} {entry.name}, sha256 {entry.sha256}. Raw text, unmodified."),
        )
    )
    return rows


def _existing_columns(cur: psycopg.Cursor, schema: str, table: str) -> list[str] | None:
    """Column names of an existing table in order, or None if it doesn't exist."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position",
        (schema, table),
    )
    cols = [c for (c,) in cur.fetchall()]
    return cols or None


def _drop_stale_tables(cur: psycopg.Cursor, keep: set[str]) -> None:
    """Drop raw tables a previous release had but this one doesn't."""
    cur.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname = %s", (config.RAW_SCHEMA,)
    )
    for (name,) in cur.fetchall():
        if name not in keep and name != LOAD_LOG:
            log.warning("dropping stale raw.%s and any views built on it", name)
            cur.execute(sql.SQL("DROP TABLE {} CASCADE").format(sql.Identifier(config.RAW_SCHEMA, name)))


def _write_load_log(cur: psycopg.Cursor, manifest: Manifest, counts: dict[str, int]) -> None:
    log_table = sql.Identifier(config.RAW_SCHEMA, LOAD_LOG)
    cur.execute(
        sql.SQL(
            """CREATE TABLE IF NOT EXISTS {} (
                   release    text        NOT NULL,
                   table_name text        NOT NULL,
                   source_file text       NOT NULL,
                   sha256     text        NOT NULL,
                   row_count  integer     NOT NULL,
                   loaded_at  timestamptz NOT NULL DEFAULT now(),
                   PRIMARY KEY (table_name)
               )"""
        ).format(log_table)
    )
    # The log describes what raw holds right now, so it is replaced wholesale.
    cur.execute(sql.SQL("TRUNCATE {}").format(log_table))
    with cur.copy(
        sql.SQL("COPY {} (release, table_name, source_file, sha256, row_count) FROM STDIN").format(log_table)
    ) as cp:
        for e in manifest.csv_files:
            cp.write_row((manifest.release, e.table, e.name, e.sha256, counts[e.table]))


def load(release: str, database_url: str | None = None) -> dict[str, int]:
    """Verify the cached release, then replace the raw schema with it."""
    manifest = verify(release)
    counts: dict[str, int] = {}
    with psycopg.connect(database_url or config.DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(config.RAW_SCHEMA)))
            for entry in manifest.csv_files:
                counts[entry.table] = _load_table(cur, release, entry)
                log.info("raw.%-20s %8d rows", entry.table, counts[entry.table])
            _drop_stale_tables(cur, set(counts))
            _write_load_log(cur, manifest, counts)
        # Leaving the connection block commits; an exception rolls everything back.
    log.info("loaded %d tables, %d rows", len(counts), sum(counts.values()))
    return counts
