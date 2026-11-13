import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
load_dotenv(BACKEND / ".env")
load_dotenv(BACKEND.parent / ".env")

import db  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def reader(anyio_backend):
    """The real read-only pool; skips when the warehouse isn't reachable."""
    try:
        await db.open_pool()
        await db.run_query("SELECT 1")
    except Exception as e:  # noqa: BLE001
        await db.close_pool()
        pytest.skip(f"warehouse not reachable as bgpt_reader ({e}); run `make build`")
    yield
    await db.close_pool()
