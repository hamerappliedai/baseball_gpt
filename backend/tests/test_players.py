"""Player search and player pages against the live warehouse (skipped when it isn't running)."""

import httpx2 as httpx  # the HTTP client the Anthropic SDK installs
import pytest

import browse
from app import app

pytestmark = pytest.mark.anyio


@pytest.fixture
async def api(reader):
    browse.clear_cache()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def search(api, q, **params):
    res = await api.get("/api/players", params={"q": q, **params})
    assert res.status_code == 200, res.text
    return [p["full_name"] for p in res.json()["results"]]


async def test_search_by_last_name_puts_famous_players_first(api):
    names = await search(api, "robinson", limit=5)
    assert "Jackie Robinson" in names and "Frank Robinson" in names
    assert "Robinson" not in names  # surname-only records rank below


async def test_search_full_name_and_case(api):
    names = await search(api, "LOU GEHRIG")
    assert names[0] == "Lou Gehrig"
    # Only other name/alias matches follow (Buck Leonard, "The Black Lou Gehrig"),
    # never loose similarity hits.
    res = (await api.get("/api/players", params={"q": "LOU GEHRIG"})).json()["results"]
    assert all(r.get("match", "name") != "similar" for r in res)


async def test_search_by_given_name(api):
    assert (await search(api, "george herman", limit=1)) == ["Babe Ruth"]


async def test_search_prefix(api):
    assert "Ted Williams" in await search(api, "ted wil")


async def test_search_treats_wildcards_literally(api):
    assert await search(api, "%%") == []
    assert await search(api, "__") == []


async def test_search_result_shape(api):
    res = await api.get("/api/players", params={"q": "gehrig"})
    p = res.json()["results"][0]
    assert p["player_id"] == "gehrilo01" and p["is_hall_of_famer"] is True
    assert (p["first_season"], p["last_season"]) == (1923, 1939)


@pytest.mark.parametrize("params", [{}, {"q": "a"}, {"q": "  a  "}, {"q": "x" * 61}, {"q": "ab", "limit": 100}])
async def test_search_rejects_bad_input(api, params):
    assert (await api.get("/api/players", params=params)).status_code == 422


async def test_player_page(api):
    res = await api.get("/api/players/gehrilo01")
    assert res.status_code == 200
    d = res.json()
    assert d["player"]["full_name"] == "Lou Gehrig" and d["player"]["hof_induction_year"] == 1939
    career = d["batting"]["career"]
    assert (career["h"], career["hr"], career["rbi"]) == (2721, 493, 1995)
    assert [s["season"] for s in d["batting"]["seasons"]] == list(range(1923, 1940))
    assert d["pitching"] is None
    assert d["fielding"][0]["position"] == "1B"
    assert {"award": "Most Valuable Player", "seasons": [1927, 1936]} in d["honors"]["awards"]
    assert d["honors"]["all_star_seasons"] == list(range(1933, 1940))
    assert {p["season"] for p in d["postseason"]["batting"]} >= {1926, 1927, 1928, 1932, 1936}


async def test_two_way_player_has_both(api):
    d = (await api.get("/api/players/ruthba01")).json()
    assert d["batting"]["career"]["hr"] == 714
    assert d["pitching"]["career"]["w"] == 94


async def test_awards_are_listed_once_per_name(api):
    awards = (await api.get("/api/players/gehrilo01")).json()["honors"]["awards"]
    names = [a["award"] for a in awards]
    assert len(names) == len(set(names))


async def test_unknown_player_is_404_and_not_cached(api):
    res = await api.get("/api/players/nobody99")
    assert res.status_code == 404
    assert ("player", "nobody99") not in browse._cache


async def test_player_page_has_etag(api):
    first = await api.get("/api/players/ruthba01")
    again = await api.get("/api/players/ruthba01", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
