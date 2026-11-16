import functools
import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")
load_dotenv(BACKEND.parent / ".env")

import psycopg  # noqa: E402

import appdb  # noqa: E402
import db  # noqa: E402


@functools.cache
def unreachable(env_var: str, probe: str = "SELECT 1") -> str | None:
    """Why the database behind env_var can't be used, or None if it can.

    Checked once per run with a short connect timeout, so tests skip in a
    second when Postgres is down instead of each waiting on the pool."""
    url = os.environ.get(env_var)
    if not url:
        return f"{env_var} is not set"
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute(probe)
    except Exception as e:  # noqa: BLE001
        return f"{type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else ''}"
    return None


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def reader(anyio_backend):
    """The real read-only pool; skips when the warehouse isn't reachable."""
    if why := unreachable("READER_DATABASE_URL"):
        pytest.skip(f"warehouse not reachable as bgpt_reader ({why}); run `make build`")
    try:
        await db.open_pool()
        await db.run_query("SELECT 1")
    except Exception as e:  # noqa: BLE001
        await db.close_pool()
        pytest.skip(f"warehouse not reachable as bgpt_reader ({e}); run `make build`")
    yield
    await db.close_pool()


@pytest.fixture
async def app_db(anyio_backend):
    """The accounts pool (bgpt_app); skips unless `make migrate` has run."""
    if why := unreachable("APP_DATABASE_URL", "SELECT 1 FROM app.users LIMIT 1"):
        pytest.skip(f"app schema not reachable as bgpt_app ({why}); run `make db-up`")
    yield
    await appdb.close_pool()
