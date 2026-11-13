"""The browse API against the live warehouse (skipped when it isn't running)."""

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


async def board(api, **params):
    res = await api.get("/api/leaderboard", params=params)
    assert res.status_code == 200, res.text
    return res.json()


async def test_meta(api):
    res = await api.get("/api/meta")
    assert res.status_code == 200
    meta = res.json()
    assert meta["seasons"] == {"first": 1871, "last": 2025}
    ids = {lg["league_id"] for lg in meta["leagues"]}
    assert {"NL", "AL", "NNL", "NAL"} <= ids
    era = next(s for s in meta["stats"]["pitching"] if s["key"] == "era")
    assert era["rate"] and era["ascending"]


async def test_default_is_single_season_home_runs(api):
    data = await board(api, limit=10)
    top = data["rows"][0]
    assert (top["rank"], top["full_name"], top["season"], top["hr"]) == (1, "Barry Bonds", 2001, 73)
    assert data["total"] > 100_000
    hr = next(c for c in data["columns"] if c["key"] == "hr")
    assert hr["highlight"] is True
    assert data["params"]["qualified"] is False


async def test_ties_share_a_rank(api):
    rows = (await board(api, limit=10))["rows"]
    sixty = [r for r in rows if r["hr"] == 60]  # Ruth 1927 and Raleigh 2025
    assert len(sixty) == 2 and {r["rank"] for r in sixty} == {9}


async def test_career_hits(api):
    top = (await board(api, stat="h", scope="career", limit=1))["rows"][0]
    assert (top["full_name"], top["h"], top["years"]) == ("Pete Rose", 4256, "1963–1986")


async def test_innings_rank_on_outs_and_show_display_text(api):
    data = await board(api, category="pitching", stat="ip", scope="career", limit=1)
    top = data["rows"][0]
    assert top["full_name"] == "Cy Young" and top["ip_display"].startswith("7356")


async def test_rate_stats_are_qualified_and_sorted(api):
    data = await board(api, category="pitching", stat="era", **{"from": 1947}, qualified="false")
    assert data["params"]["qualified"] is True  # forced on for rate stats
    eras = [r["era"] for r in data["rows"]]
    assert eras == sorted(eras)
    assert all(r["season"] >= 1947 for r in data["rows"])
    assert any("1 inning pitched per team game" in n for n in data["notes"])


async def test_negro_leagues_filter(api):
    meta = (await api.get("/api/meta")).json()
    negro = {lg["league_id"] for lg in meta["leagues"]
             if lg["is_negro_leagues"] and not lg["is_independent_clubs"]}
    rows = (await board(api, league="negro", limit=100))["rows"]
    assert rows and {r["league"] for r in rows} <= negro


async def test_single_league_filter(api):
    rows = (await board(api, stat="avg", league="AL", **{"from": 1941, "to": 1941}, limit=1))["rows"]
    assert rows[0]["full_name"] == "Ted Williams" and rows[0]["league"] == "AL"


async def test_pagination_continues_the_ranking(api):
    page2 = await board(api, stat="hr", scope="career", limit=50, offset=50)
    assert page2["rows"][0]["rank"] >= 50


@pytest.mark.parametrize("params", [
    {"stat": "war"},                              # not in Lahman / not in the catalogue
    {"category": "fielding"},
    {"scope": "decade"},
    {"league": "XX"},
    {"league": "AL'; DROP TABLE marts.players; --"},
    {"scope": "career", "league": "NL"},
    {"from": 1990, "to": 1980},
    {"limit": 1000},
    {"offset": -1},
])
async def test_invalid_params_are_rejected(api, params):
    res = await api.get("/api/leaderboard", params=params)
    assert res.status_code == 422


async def test_etag_returns_304(api):
    first = await api.get("/api/leaderboard", params={"limit": 5})
    assert "max-age" in first.headers["cache-control"]
    again = await api.get("/api/leaderboard", params={"limit": 5},
                          headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


async def test_unknown_api_path_is_404_not_the_app(api):
    res = await api.get("/api/nope")
    assert res.status_code == 404
