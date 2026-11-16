"""Hybrid player search (phase 4). Skipped unless `bgpt-pipeline embed` has run
and the embedding model is available locally."""

import httpx2 as httpx
import pytest

import browse
import search as hybrid
from app import app

pytestmark = pytest.mark.anyio


@pytest.fixture
async def api(reader):
    if not await hybrid.vectors_ready():
        pytest.skip("vectors.player_aliases not built with the backend's model (run `make embed`)")
    try:
        await hybrid.embed_query("warm up")
    except Exception as e:  # noqa: BLE001 - model not downloadable here
        pytest.skip(f"embedding model unavailable: {e}")
    browse.clear_cache()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def search(api, q, limit=5):
    res = await api.get("/api/players", params={"q": q, "limit": limit})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["mode"] == "hybrid"
    return body["results"]


@pytest.mark.parametrize("q, who, alias", [
    ("iron horse", "Lou Gehrig", "The Iron Horse"),
    ("big papi", "David Ortiz", "Big Papi"),
    ("say hey", "Willie Mays", "The Say Hey Kid"),
    ("yaz", "Carl Yastrzemski", "Yaz"),
])
async def test_nickname_finds_player_and_says_why(api, q, who, alias):
    top = (await search(api, q))[0]
    assert top["full_name"] == who
    assert top["matched_alias"] == alias


@pytest.mark.parametrize("q, who", [
    ("lou gherig", "Lou Gehrig"),
    ("mickey mantel", "Mickey Mantle"),
    ("derek jeeter", "Derek Jeter"),
    ("hammering hank", "Hank Aaron"),
    ("mr october", "Reggie Jackson"),
])
async def test_misspellings_and_loose_phrasing(api, q, who):
    top = (await search(api, q))[0]
    assert top["full_name"] == who
    assert top["match"] in ("alias", "similar")


async def test_accent_insensitive(api):
    assert (await search(api, "acuna"))[0]["full_name"] == "Ronald Acuña"


async def test_exact_names_still_rank_by_career(api):
    names = [r["full_name"] for r in await search(api, "robinson")]
    assert "Jackie Robinson" in names and "Frank Robinson" in names
    top = (await search(api, "pujols"))[0]
    assert top["full_name"] == "Albert Pujols" and top["match"] == "name" and top["matched_alias"] is None


@pytest.mark.parametrize("q", ["zzzz", "qwerty asdf", "50%", "%%"])
async def test_junk_returns_nothing(api, q):
    assert await search(api, q) == []
