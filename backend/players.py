"""Player search and player pages for the browse API (no AI).

    GET /api/players?q=gehrig        typeahead search, best match first
    GET /api/players/{player_id}     everything for one player page

Search is hybrid (search.py): name matching, trigram spelling similarity and
sentence-transformers embeddings over vectors.player_aliases, which includes
curated nicknames. If the embeddings aren't built yet it falls back to plain
SQL name matching, with the same response shape.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Request, Response

import db
import search as hybrid
from browse import cached, json_response

router = APIRouter(prefix="/api/players", tags=["players"])


# --- Search -------------------------------------------------------------------------

# Fallback when the embeddings aren't available. Ranked best first: exact full or last name, prefix, anywhere in the name, then
# given name ("George Herman Ruth"). Ties go to the player with more games, so
# "Robinson" finds Brooks, Frank and Jackie before the rest.
_SEARCH_SQL = """
SELECT player_id, full_name, first_season, last_season, primary_position, teams,
       is_hall_of_famer, played_negro_leagues,
       CASE
         -- One tier: some Negro Leagues players are recorded by surname only,
         -- and "Robinson" shouldn't put them ahead of Jackie Robinson.
         WHEN lower(full_name) = %(exact)s OR lower(name_last) = %(exact)s THEN 0
         WHEN full_name ILIKE %(prefix)s OR name_last ILIKE %(prefix)s THEN 1
         WHEN full_name ILIKE %(anywhere)s THEN 2
         ELSE 3
       END AS match_rank
FROM marts.players
WHERE is_player
  AND (full_name ILIKE %(anywhere)s
       OR name_given ILIKE %(anywhere)s
       OR (name_given || ' ' || name_last) ILIKE %(anywhere)s)
ORDER BY match_rank, games_played DESC NULLS LAST, full_name, player_id
LIMIT %(limit)s
"""


@router.get("")
async def search(
    request: Request,
    q: str = Query(..., min_length=2, max_length=60, description="Part of a player's name"),
    limit: int = Query(10, ge=1, le=25),
) -> Response:
    """Players matching `q` by name, nickname, spelling or meaning, best match first.

    Each result says how it matched: "name", "alias" (with matched_alias, e.g.
    "The Iron Horse") or "similar" (a close spelling or meaning).
    """
    text = " ".join(q.split())  # collapse whitespace
    if len(text) < 2:
        raise HTTPException(status_code=422, detail="Type at least two characters.")
    if await hybrid.vectors_ready():
        rows, mode = await hybrid.hybrid_search(text, limit), "hybrid"
    else:
        rows, mode = await _sql_search(text, limit), "sql"
    return json_response(request, {"query": text, "mode": mode, "results": rows})


async def _sql_search(text: str, limit: int) -> list[dict[str, Any]]:
    esc = hybrid.like_escape(text)
    rows = await db.fetch(_SEARCH_SQL, {
        "exact": text.lower(), "prefix": f"{esc}%", "anywhere": f"%{esc}%", "limit": limit,
    })
    for r in rows:
        r.pop("match_rank")
        r["match"], r["matched_alias"] = "name", None
    return rows


# --- Player page ----------------------------------------------------------------------

_BIO_SQL = """
SELECT player_id, full_name, name_given, birth_date, birth_city, birth_state, birth_country,
       death_date, death_city, death_state, death_country, bats, throws, height_in, weight_lbs,
       debut_date, final_game_date, first_season, last_season, seasons_played, games_played,
       primary_position, teams, played_negro_leagues, is_player, is_manager,
       is_hall_of_famer, hof_induction_year, hof_category, hof_voted_by, bbref_id
FROM marts.players WHERE player_id = %(id)s
"""

_BATTING_COLS = ("g, pa, ab, r, h, doubles, triples, hr, rbi, sb, cs, bb, so, "
                 "avg, obp, slg, ops, tb")
_PITCHING_COLS = ("w, l, win_pct, era, g, gs, cg, sho, sv, ipouts, ip_display, h, r, er, "
                  "hr, bb, so, whip, so9, bb9")

_QUERIES: dict[str, str] = {
    "batting_seasons": f"""
        SELECT season, team_ids, league_ids, {_BATTING_COLS}, qualifies_batting_title AS qualified
        FROM marts.batting_seasons WHERE player_id = %(id)s ORDER BY season""",
    "batting_career": f"""
        SELECT first_season, last_season, seasons, {_BATTING_COLS}
        FROM marts.batting_careers WHERE player_id = %(id)s""",
    "pitching_seasons": f"""
        SELECT season, team_ids, league_ids, {_PITCHING_COLS}, qualifies_era_title AS qualified
        FROM marts.pitching_seasons WHERE player_id = %(id)s ORDER BY season""",
    "pitching_career": f"""
        SELECT first_season, last_season, seasons, {_PITCHING_COLS}
        FROM marts.pitching_careers WHERE player_id = %(id)s""",
    # Fielding by position over the career, most games first.
    "fielding": """
        SELECT position, min(season) AS first_season, max(season) AS last_season,
               sum(g) AS g, sum(gs) AS gs, sum(po) AS po, sum(a) AS a, sum(e) AS e, sum(dp) AS dp,
               round((sum(po) + sum(a))::numeric / nullif(sum(po) + sum(a) + sum(e), 0), 3)
                 AS fielding_pct
        FROM marts.fielding_seasons WHERE player_id = %(id)s
        GROUP BY position ORDER BY sum(g) DESC NULLS LAST, position""",
    "postseason_batting": """
        SELECT season, round, round_name, team_id, g, pa, ab, r, h, doubles, triples, hr, rbi,
               sb, bb, so, avg, obp, slg, ops
        FROM marts.postseason_batting WHERE player_id = %(id)s
        ORDER BY season, round_name""",
    "postseason_pitching": """
        SELECT season, round, round_name, team_id, w, l, g, gs, sv, ipouts, ip_display, h, er,
               bb, so, era, whip
        FROM marts.postseason_pitching WHERE player_id = %(id)s
        ORDER BY season, round_name""",
    # An award can be listed once per league (e.g. AL and ML), so group by name.
    "awards": """
        SELECT award, array_agg(DISTINCT season ORDER BY season) AS seasons
        FROM marts.awards WHERE player_id = %(id)s
        GROUP BY award ORDER BY min(season), award""",
    "all_star": """
        SELECT array_agg(DISTINCT season ORDER BY season) AS seasons
        FROM marts.all_star_selections WHERE player_id = %(id)s""",
    "award_voting": """
        SELECT award, season, league_id, finish, vote_share, first_place_votes
        FROM marts.award_voting WHERE player_id = %(id)s AND finish <= 5
        ORDER BY season, award""",
    "hall_of_fame_voting": """
        SELECT season, voted_by, ballots, votes, votes_needed, vote_pct, is_inducted
        FROM marts.hall_of_fame_voting WHERE player_id = %(id)s AND category = 'Player'
        ORDER BY season, voted_by""",
}


async def _build_player(player_id: str) -> dict[str, Any] | None:
    data = await db.fetch_many({"bio": _BIO_SQL, **_QUERIES}, {"id": player_id})
    bio = data["bio"]
    if not bio:
        return None

    def one(rows):
        return rows[0] if rows else None

    return {
        "player": bio[0],
        "batting": {"seasons": data["batting_seasons"], "career": one(data["batting_career"])}
        if data["batting_seasons"] else None,
        "pitching": {"seasons": data["pitching_seasons"], "career": one(data["pitching_career"])}
        if data["pitching_seasons"] else None,
        "fielding": data["fielding"],
        "postseason": {"batting": data["postseason_batting"], "pitching": data["postseason_pitching"]},
        "honors": {
            "awards": data["awards"],
            "all_star_seasons": (one(data["all_star"]) or {}).get("seasons") or [],
            "award_voting": data["award_voting"],
            "hall_of_fame_voting": data["hall_of_fame_voting"],
        },
    }


@router.get("/{player_id}")
async def player(
    request: Request,
    player_id: str = Path(..., min_length=1, max_length=20),
) -> Response:
    """One player's page: bio, season and career stats, fielding, postseason, honors."""
    data = await cached(("player", player_id), lambda: _build_player(player_id))
    if data is None:
        raise HTTPException(status_code=404, detail=f"No player with id {player_id!r}.")
    return json_response(request, data)
