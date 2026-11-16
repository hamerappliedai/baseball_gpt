"""Connection pool for the `app` schema (accounts, sessions, usage).

Runs as bgpt_app, which can read and write the app schema and nothing else
(db/roles.sql). The warehouse pool in db.py runs as bgpt_reader, which can't
see app at all, so Claude's SQL can never reach user data.
"""

from __future__ import annotations

import os
from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

_pool: AsyncConnectionPool | None = None


def app_url() -> str:
    url = os.environ.get("APP_DATABASE_URL")
    if not url:
        raise RuntimeError("APP_DATABASE_URL is not set (see .env.example)")
    return url


async def open_pool() -> AsyncConnectionPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(app_url(), min_size=1, max_size=5, open=False, timeout=10,
                                    kwargs={"autocommit": True, "row_factory": dict_row,
                                            "connect_timeout": 5})
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def fetch(query: str, params: dict[str, Any] | tuple | None = None) -> list[dict[str, Any]]:
    pool = await open_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(query, params)
        return await cur.fetchall() if cur.description else []


async def fetch_one(query: str, params: dict[str, Any] | tuple | None = None) -> dict[str, Any] | None:
    rows = await fetch(query, params)
    return rows[0] if rows else None
