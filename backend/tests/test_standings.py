"""Season standings against the live warehouse (skipped when it isn't running)."""

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


async def standings(api, season):
    res = await api.get(f"/api/standings/{season}")
    assert res.status_code == 200, res.text
    return res.json()


def league(data, league_id):
    return next(lg for lg in data["leagues"] if lg["league_id"] == league_id)


async def test_1927_yankees_win_the_al_by_19(api):
    data = await standings(api, 1927)
    al = league(data, "AL")
    assert len(al["divisions"]) == 1 and al["divisions"][0]["name"] == ""  # no divisions yet
    teams = al["divisions"][0]["teams"]
    assert (teams[0]["team_id"], teams[0]["w"], teams[0]["l"], teams[0]["gb"]) == ("NYA", 110, 44, 0)
    assert teams[1]["gb"] == 19
    assert data["champion"]["winner_team_id"] == "NYA"


async def test_negro_leagues_and_their_world_series(api):
    data = await standings(api, 1927)
    nnl = league(data, "NNL")
    assert nnl["is_negro_leagues"] is True
    rounds = {s["round"] for stage in data["postseason"] for s in stage["series"]}
    assert {"WS", "NWS"} <= rounds
    # Major leagues come before the Negro Leagues.
    ids = [lg["league_id"] for lg in data["leagues"]]
    assert ids.index("AL") < ids.index("NNL")


async def test_2025_divisions_and_tiebreak_order(api):
    data = await standings(api, 2025)
    al = league(data, "AL")
    assert [d["name"] for d in al["divisions"]] == ["East", "Central", "West"]
    east = al["divisions"][0]["teams"]
    # Toronto won the East on the tiebreaker at 94-68; New York is 0 GB.
    assert [(t["team_id"], t["w"], t["l"], t["gb"]) for t in east[:2]] == [("TOR", 94, 68, 0), ("NYA", 94, 68, 0)]
    assert east[0]["won_division"] is True and east[1]["won_wild_card"] is True
    assert sum(t["w"] for t in east) + sum(t["l"] for t in east) == 5 * 162


async def test_2025_postseason_stages(api):
    data = await standings(api, 2025)
    assert [(s["stage"], len(s["series"])) for s in data["postseason"]] == [
        ("Wild Card", 4), ("Division Series", 4), ("League Championship", 2), ("World Series", 1)]
    champ = data["champion"]
    assert (champ["winner_team_id"], champ["loser_team_id"], champ["wins"], champ["losses"]) == ("LAN", "TOR", 4, 3)


async def test_pythagorean_record_adds_up(api):
    for t in league(await standings(api, 2025), "NL")["divisions"][0]["teams"]:
        assert t["pythag_w"] + t["pythag_l"] == t["w"] + t["l"]


async def test_1994_strike_has_no_postseason(api):
    data = await standings(api, 1994)
    assert data["postseason"] == [] and data["champion"] is None


async def test_first_season(api):
    data = await standings(api, 1871)
    assert [lg["league_id"] for lg in data["leagues"]] == ["NA"]
    assert data["seasons"] == {"first": 1871, "last": 2025}


@pytest.mark.parametrize("season,status", [(1870, 404), (2026, 404), (1500, 422), ("abc", 422)])
async def test_bad_seasons(api, season, status):
    assert (await api.get(f"/api/standings/{season}")).status_code == status
