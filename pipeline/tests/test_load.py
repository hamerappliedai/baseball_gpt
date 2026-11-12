"""Integration tests against the docker compose Postgres. Skipped if it isn't running."""

import uuid

import psycopg
import pytest

from baseball_pipeline import config, load
from baseball_pipeline.manifest import FileEntry


@pytest.fixture
def db(monkeypatch):
    try:
        conn = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=2)
    except psycopg.OperationalError:
        pytest.skip("Postgres not reachable (run `docker compose up -d`)")
    schema = f"raw_test_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(config, "RAW_SCHEMA", schema)
    yield conn, schema
    conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
    conn.close()


def q(conn, sql, *params):
    return conn.execute(sql, params).fetchall()


def test_load_strips_bom_and_maps_empty_to_null(release, db):
    conn, schema = db
    counts = load.load("1999")
    assert counts == {"people": 3, "batting": 2}

    cols = q(conn, "SELECT column_name FROM information_schema.columns WHERE table_schema=%s "
                   "AND table_name='people' ORDER BY ordinal_position", schema)
    assert cols[0] == ("id",)  # not '﻿id'

    rows = q(conn, f'SELECT playerid, namefirst, namelast, deathyear FROM "{schema}".people ORDER BY id')
    assert rows == [
        ("ruthba01", "Babe", "Ruth", "1948"),
        ("judgeaa01", "Aaron", "Judge, Jr.", None),  # unquoted empty -> NULL
        ("oddca01", "Car\r\nl", "Odd", None),  # quoted "" -> NULL
    ]
    assert q(conn, f'SELECT "2b", "3b" FROM "{schema}".batting ORDER BY yearid') == [("29", "8"), (None, None)]

    log = q(conn, f'SELECT table_name, row_count FROM "{schema}"._load_log ORDER BY table_name')
    assert log == [("batting", 2), ("people", 3)]


def test_reload_is_idempotent_and_drops_stale_tables(release, db):
    conn, schema = db
    load.load("1999")
    conn.execute(f'CREATE TABLE "{schema}".gone (x int)')
    load.load("1999")
    tables = {t for (t,) in q(conn, "SELECT tablename FROM pg_tables WHERE schemaname=%s", schema)}
    assert tables == {"people", "batting", "_load_log"}


def test_reload_keeps_dependent_views(release, db):
    # dbt's staging views select from raw tables; a reload must not break them.
    conn, schema = db
    load.load("1999")
    view = f'"{schema}".v_people'
    conn.execute(f'CREATE VIEW {view} AS SELECT playerid FROM "{schema}".people')
    load.load("1999")
    assert len(q(conn, f"SELECT * FROM {view}")) == 3
    conn.execute(f"DROP VIEW {view}")


def test_reload_recreates_table_when_columns_change(release, db, monkeypatch):
    conn, schema = db
    load.load("1999")
    conn.execute(f'ALTER TABLE "{schema}".people ADD COLUMN extra text')
    conn.execute(f'CREATE VIEW "{schema}".v_extra AS SELECT extra FROM "{schema}".people')
    load.load("1999")
    cols = [c for (c,) in q(conn, "SELECT column_name FROM information_schema.columns WHERE "
                                  "table_schema=%s AND table_name='people'", schema)]
    assert "extra" not in cols
    views = q(conn, "SELECT viewname FROM pg_views WHERE schemaname=%s", schema)
    assert views == []  # dropped with the old table; dbt rebuilds real ones


def test_failed_load_leaves_previous_data(release, db, monkeypatch):
    conn, schema = db
    load.load("1999")
    conn.execute(f"""UPDATE "{schema}".people SET namelast = 'marker' WHERE playerid = 'ruthba01'""")

    # Batting loads fine, then people (loaded second) fails its row-count check
    # mid-transaction. Bypass the file verification so the DB check is what fails.
    people: FileEntry = next(f for f in release.files if f.table == "people")
    people.rows = 99
    release.files.sort(key=lambda f: f.table != "batting")
    monkeypatch.setattr(load, "verify", lambda r: release)
    with pytest.raises(load.LoadError, match="loaded 3 rows, manifest says 99"):
        load.load("1999")

    # The whole load rolled back: the marker row from the earlier load survives.
    assert q(conn, f"""SELECT namelast FROM "{schema}".people WHERE playerid = 'ruthba01'""") == [("marker",)]
