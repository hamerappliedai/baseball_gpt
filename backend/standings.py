"""Season standings and postseason results for the browse API (no AI).

    GET /api/standings/{season}

Standings are grouped by league, then division (pre-1969 leagues have none).
Teams are ordered by Lahman's division_rank, which records tiebreakers that
the won-lost record alone can't (e.g. Toronto over New York in the 2025 AL
East at 94-68 each).
"""

from __future__ import annotations

from itertools import groupby
from typing import Any

from fastapi import APIRouter, HTTPException, Path, Request, Response

import db
from browse import cached, get_meta, json_response

router = APIRouter(prefix="/api/standings", tags=["standings"])

DIVISION_NAMES = {"E": "East", "C": "Central", "W": "West"}

# Games behind the division (or league) leader: half the difference in wins
# plus half the difference in losses. The leader is division_rank 1.
_TEAMS_SQL = """
SELECT t.league_id, t.division_id, t.division_rank, t.team_id, t.team_name, t.franchise_id,
       t.g, t.w, t.l, t.win_pct,
       ((first_value(t.w) OVER div - t.w) + (t.l - first_value(t.l) OVER div)) / 2.0 AS gb,
       t.r, t.ra, t.run_diff,
       round(t.pythag_win_pct * (t.w + t.l))::int AS pythag_w,
       (t.w + t.l) - round(t.pythag_win_pct * (t.w + t.l))::int AS pythag_l,
       t.won_division, t.won_wild_card, t.won_pennant, t.won_world_series,
       t.park_name, t.attendance,
       l.league_name, l.is_negro_leagues, l.is_independent_clubs, l.first_season AS league_first
FROM marts.team_seasons t
JOIN marts.leagues l USING (league_id)
WHERE t.season = %(season)s
WINDOW div AS (PARTITION BY t.league_id, t.division_id ORDER BY t.division_rank, t.win_pct DESC)
ORDER BY l.is_independent_clubs, l.is_negro_leagues, l.first_season, t.league_id,
         CASE t.division_id WHEN 'E' THEN 1 WHEN 'C' THEN 2 WHEN 'W' THEN 3 ELSE 0 END,
         t.division_rank, t.win_pct DESC
"""

_SERIES_SQL = """
SELECT stage, stage_order, round, round_name, winner_team_id, winner_team_name,
       winner_league_id, loser_team_id, loser_team_name, loser_league_id, wins, losses, ties
FROM marts.postseason_series
WHERE season = %(season)s
ORDER BY stage_order, round
"""

_TEAM_KEYS = ("division_rank", "team_id", "team_name", "franchise_id", "g", "w", "l", "win_pct",
              "gb", "r", "ra", "run_diff", "pythag_w", "pythag_l", "won_division",
              "won_wild_card", "won_pennant", "won_world_series", "park_name", "attendance")


def _group_standings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    leagues = []
    for league_id, league_rows in groupby(rows, key=lambda r: r["league_id"]):
        league_rows = list(league_rows)
        first = league_rows[0]
        divisions = []
        for division_id, div_rows in groupby(league_rows, key=lambda r: r["division_id"]):
            divisions.append({
                "division_id": division_id,
                "name": DIVISION_NAMES.get(division_id, division_id or ""),
                "teams": [{k: r[k] for k in _TEAM_KEYS} for r in div_rows],
            })
        leagues.append({
            "league_id": league_id,
            "league_name": first["league_name"],
            "is_negro_leagues": first["is_negro_leagues"],
            "is_independent_clubs": first["is_independent_clubs"],
            "divisions": divisions,
        })
    return leagues


async def _build_standings(season: int) -> dict[str, Any] | None:
    data = await db.fetch_many({"teams": _TEAMS_SQL, "series": _SERIES_SQL}, {"season": season})
    if not data["teams"]:
        return None

    stages = []
    for (stage_order, stage), series in groupby(data["series"], key=lambda s: (s["stage_order"], s["stage"])):
        stages.append({"stage": stage, "stage_order": stage_order, "series": list(series)})

    champions = [s for s in data["series"] if s["round"] == "WS"]
    return {
        "season": season,
        "leagues": _group_standings(data["teams"]),
        "postseason": stages,
        "champion": champions[0] if champions else None,
    }


@router.get("/{season}")
async def standings(request: Request, season: int = Path(..., ge=1800, le=2100)) -> Response:
    """Final standings for one season, plus its postseason series."""
    meta = await get_meta()
    first, last = meta["seasons"]["first"], meta["seasons"]["last"]
    if not first <= season <= last:
        raise HTTPException(status_code=404, detail=f"No standings for {season}; seasons run {first}–{last}.")
    data = await cached(("standings", season), lambda: _build_standings(season))
    if data is None:
        raise HTTPException(status_code=404, detail=f"No standings for {season}.")
    return json_response(request, {**data, "seasons": meta["seasons"]})
