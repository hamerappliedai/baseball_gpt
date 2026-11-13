"""Read-only access to the warehouse.

Two entry points, both running as the bgpt_reader role (SELECT on marts only,
see db/roles.sql) inside a READ ONLY transaction with a statement timeout that
is always rolled back:

- run_query(sql): Claude's arbitrary SQL, through a server-side cursor so a
  huge result is never pulled into memory, capped at MAX_ROWS.
- fetch(query, params): the fixed, parameterized queries behind the browse API.

The role's privileges are the security boundary; the rest keeps one bad query
from tying up the database or the app.
"""

from __future__ import annotations

import datetime as dt
import decimal
import os
from dataclasses import dataclass

from typing import Any

import psycopg
from psycopg import sql as pgsql
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

STATEMENT_TIMEOUT_MS = int(os.environ.get("SQL_TIMEOUT_MS", "5000"))
MAX_ROWS = int(os.environ.get("SQL_MAX_ROWS", "200"))
MAX_CELL_CHARS = 200

_pool: AsyncConnectionPool | None = None


def reader_url() -> str:
    url = os.environ.get("READER_DATABASE_URL")
    if not url:
        raise RuntimeError("READER_DATABASE_URL is not set (see .env.example)")
    return url


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(reader_url(), min_size=1, max_size=5, open=False)
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool  # more rows existed than MAX_ROWS

    def to_text(self) -> str:
        """Render for Claude: a pipe-separated table plus a row-count line."""
        if not self.columns:
            return "Query returned no columns."
        lines = [" | ".join(self.columns)]
        lines += [" | ".join(_cell(v) for v in row) for row in self.rows]
        n = len(self.rows)
        if self.truncated:
            lines.append(f"({n} rows shown; more rows exist. Add filters, aggregate, or ORDER BY ... LIMIT.)")
        else:
            lines.append(f"({n} row{'s' if n != 1 else ''})")
        return "\n".join(lines)


def _cell(v: object) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, decimal.Decimal):
        s = format(v.normalize(), "f") if v == v.to_integral() else str(v)
    elif isinstance(v, (dt.date, dt.datetime)):
        s = v.isoformat()
    else:
        s = str(v)
    s = s.replace("\n", " ").replace("|", "/")
    return s if len(s) <= MAX_CELL_CHARS else s[: MAX_CELL_CHARS - 1] + "…"


class QueryError(Exception):
    """A query Postgres rejected; the message is safe to show Claude."""


async def run_query(sql: str) -> QueryResult:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise QueryError("Empty query.")
    pool = await open_pool()
    async with pool.connection() as conn:
        try:
            async with conn.transaction(force_rollback=True):
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
                # A named (server-side) cursor only accepts SELECT / VALUES
                # (including WITH ... SELECT), and fetches only what we read.
                async with conn.cursor(name="claude_query") as cur:
                    await cur.execute(sql)
                    rows = await cur.fetchmany(MAX_ROWS + 1)
                    columns = [d.name for d in cur.description or []]
        except psycopg.errors.QueryCanceled:
            raise QueryError(
                f"Query cancelled after {STATEMENT_TIMEOUT_MS / 1000:g}s. Simplify it or add filters."
            ) from None
        except psycopg.Error as e:
            diag = e.diag
            msg = diag.message_primary or str(e)
            if diag.message_hint:
                msg += f" (hint: {diag.message_hint})"
            raise QueryError(msg) from None
    return QueryResult(columns, [tuple(r) for r in rows[:MAX_ROWS]], len(rows) > MAX_ROWS)


async def fetch(query: str | pgsql.Composable, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Run one of the app's own parameterized queries and return rows as dicts.

    Never pass user input into `query` itself: values go in `params`, and any
    identifiers must come from an allow-list and be composed with psycopg.sql.
    """
    pool = await open_pool()
    async with pool.connection() as conn:
        async with conn.transaction(force_rollback=True):
            await conn.execute("SET TRANSACTION READ ONLY")
            await conn.execute(f"SET LOCAL statement_timeout = {STATEMENT_TIMEOUT_MS}")
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                return await cur.fetchall()
