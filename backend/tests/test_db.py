"""run_query against the real warehouse, as the read-only role."""

import pytest

import db

pytestmark = pytest.mark.anyio


async def test_select_returns_rows(reader):
    r = await db.run_query("SELECT player_id, hr FROM batting_careers WHERE player_id = 'ruthba01';")
    assert r.columns == ["player_id", "hr"]
    assert r.rows == [("ruthba01", 714)]
    assert "ruthba01 | 714" in r.to_text() and "(1 row)" in r.to_text()


async def test_rows_are_capped(reader, monkeypatch):
    monkeypatch.setattr(db, "MAX_ROWS", 5)
    r = await db.run_query("SELECT player_id FROM players")
    assert len(r.rows) == 5 and r.truncated
    assert "more rows exist" in r.to_text()


@pytest.mark.parametrize("sql", [
    "INSERT INTO leagues VALUES ('XX', 'x', false, false, 1, 1)",
    "DELETE FROM players",
    "DROP TABLE players",
    "CREATE TABLE t (x int)",
    "UPDATE players SET full_name = 'x'",
])
async def test_writes_are_rejected(reader, sql):
    with pytest.raises(db.QueryError):
        await db.run_query(sql)


async def test_data_modifying_cte_is_rejected(reader):
    with pytest.raises(db.QueryError):
        await db.run_query("WITH d AS (DELETE FROM players RETURNING *) SELECT count(*) FROM d")


@pytest.mark.parametrize("sql", ["SELECT * FROM raw.people", "SELECT * FROM staging.stg_people"])
async def test_only_marts_are_visible(reader, sql):
    with pytest.raises(db.QueryError, match="permission denied"):
        await db.run_query(sql)


async def test_multiple_statements_are_rejected(reader):
    with pytest.raises(db.QueryError):
        await db.run_query("SELECT 1; DELETE FROM players")


async def test_timeout_cancels_slow_queries(reader, monkeypatch):
    monkeypatch.setattr(db, "STATEMENT_TIMEOUT_MS", 200)
    with pytest.raises(db.QueryError, match="cancelled"):
        await db.run_query("SELECT pg_sleep(2)")


async def test_settings_changed_by_a_query_do_not_leak(reader):
    # set_config(..., false) is session-level, but the transaction is rolled back.
    await db.run_query("SELECT set_config('statement_timeout', '0', false)")
    r = await db.run_query("SELECT current_setting('statement_timeout')")
    assert r.rows[0][0] != "0"


async def test_errors_are_readable(reader):
    with pytest.raises(db.QueryError, match='column "nope" does not exist'):
        await db.run_query("SELECT nope FROM players")


def test_cell_formatting():
    import decimal, datetime
    r = db.QueryResult(["a", "b", "c", "d"], [(decimal.Decimal("0.406"), decimal.Decimal("58"),
                                                None, datetime.date(1927, 9, 30))], False)
    assert r.to_text().splitlines()[1] == "0.406 | 58 | NULL | 1927-09-30"
