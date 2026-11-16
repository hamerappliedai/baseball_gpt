"""Apply the app schema's SQL migrations (db/migrations/NNN_name.sql) in order.

    bgpt-pipeline migrate          # after `make db-up`, as the database owner

Each file runs in its own transaction together with its row in
app.schema_migrations, so a failed migration leaves nothing half-applied and
is retried next time. Applied files are never re-run; a changed checksum for
an applied file is an error (add a new migration instead of editing one).
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path

import psycopg

from .config import DATABASE_URL

log = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "db" / "migrations"
NAME = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")


class MigrationError(Exception):
    pass


def discover(directory: Path = MIGRATIONS_DIR) -> list[tuple[int, str, str]]:
    """(version, filename, sql) for every migration file, in version order."""
    found = []
    for path in sorted(directory.glob("*.sql")):
        m = NAME.match(path.name)
        if not m:
            raise MigrationError(f"bad migration file name {path.name!r} (want NNN_name.sql)")
        found.append((int(m.group(1)), path.name, path.read_text()))
    versions = [v for v, _, _ in found]
    if len(set(versions)) != len(versions):
        raise MigrationError("two migration files share a version number")
    return found


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def migrate(database_url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply pending migrations. Returns the names of the files applied."""
    migrations = discover(directory)
    applied_now = []
    with psycopg.connect(database_url or DATABASE_URL, autocommit=True) as conn:
        conn.execute("CREATE SCHEMA IF NOT EXISTS app")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS app.schema_migrations (
                version     integer PRIMARY KEY,
                name        text NOT NULL,
                checksum    text NOT NULL,
                applied_at  timestamptz NOT NULL DEFAULT now()
            )""")
        # Only the owner needs the ledger (roles.sql grants bgpt_app the rest of app).
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'bgpt_app'").fetchone():
            conn.execute("REVOKE ALL ON app.schema_migrations FROM bgpt_app")
        done = {v: (n, c) for v, n, c in conn.execute(
            "SELECT version, name, checksum FROM app.schema_migrations")}
        for version, name, sql in migrations:
            if version in done:
                if done[version][1] != _checksum(sql):
                    raise MigrationError(f"{name} changed after it was applied; add a new migration instead")
                continue
            log.info("applying %s", name)
            with conn.transaction():
                conn.execute(sql)
                conn.execute("INSERT INTO app.schema_migrations (version, name, checksum) VALUES (%s, %s, %s)",
                             (version, name, _checksum(sql)))
            applied_now.append(name)
    log.info("%d migration(s) applied, %d already in place", len(applied_now), len(migrations) - len(applied_now))
    return applied_now
