"""The browse API: token-free pages served straight from the marts.

Users never send SQL. Each endpoint runs a fixed, parameterized query; values
that choose a table or column (stat, scope, league) are checked against the
allow-lists in stats.py and composed with psycopg.sql.Identifier.

The data only changes when a new release is loaded (which means a restart), so
responses are kept in a small in-memory cache and sent with an ETag and a
Cache-Control header that lets a browser or CDN reuse them.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from psycopg import sql

import db
from stats import (CATALOGUE, CONTEXT, DEFAULT_STAT, ERAS, QUALIFIER, QUALIFIER_NOTE, TABLES,
                   Category, Scope)

router = APIRouter(prefix="/api", tags=["browse"])

CACHE_SECONDS = int(os.environ.get("BROWSE_CACHE_SECONDS", "3600"))
CACHE_ENTRIES = 512
MAX_LIMIT = 100

_cache: OrderedDict[tuple, Any] = OrderedDict()


async def cached(key: tuple, build: Callable[[], Awaitable[Any]]) -> Any:
    """A bounded LRU cache of built responses, keyed on validated parameters.

    None (e.g. an unknown player) is never cached, so random lookups can't
    push real pages out of the cache.
    """
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    value = await build()
    if value is None:
        return None
    _cache[key] = value
    if len(_cache) > CACHE_ENTRIES:
        _cache.popitem(last=False)
    return value


def clear_cache() -> None:
    _cache.clear()


def json_response(request: Request, payload: Any) -> Response:
    """JSON with an ETag; answers 304 when the client already has this body."""
    body = json.dumps(jsonable_encoder(payload), separators=(",", ":")).encode()
    etag = '"' + hashlib.sha256(body).hexdigest()[:20] + '"'
    headers = {"ETag": etag, "Cache-Control": f"public, max-age={CACHE_SECONDS}"}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(body, media_type="application/json", headers=headers)


def _invalid(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail=message)


# --- /api/meta ---------------------------------------------------------------

async def _build_meta() -> dict:
    leagues = await db.fetch(
        "SELECT league_id, league_name, is_negro_leagues, is_independent_clubs, "
        "first_season, last_season FROM marts.leagues ORDER BY first_season, league_id"
    )
    span = (await db.fetch("SELECT min(season) AS first, max(season) AS last FROM marts.team_seasons"))[0]
    return {
        "seasons": {"first": span["first"], "last": span["last"]},
        "leagues": leagues,
        "eras": ERAS,
        "stats": {cat: [s.public() for s in stats.values()] for cat, stats in CATALOGUE.items()},
        "default_stat": DEFAULT_STAT,
    }


async def get_meta() -> dict:
    return await cached(("meta",), _build_meta)


@router.get("/meta")
async def meta(request: Request) -> Response:
    """Everything the browse pages need for their dropdowns."""
    return json_response(request, await get_meta())


# --- /api/leaderboard ----------------------------------------------------------

def _negro_league_ids(meta: dict) -> list[str]:
    # The organized Negro Leagues; independent clubs are excluded (they never qualify).
    return [lg["league_id"] for lg in meta["leagues"]
            if lg["is_negro_leagues"] and not lg["is_independent_clubs"]]


@router.get("/leaderboard")
async def leaderboard(
    request: Request,
    category: Category = "batting",
    stat: str | None = None,
    scope: Scope = "season",
    from_: int | None = Query(None, alias="from", ge=1800, le=2100),
    to: int | None = Query(None, ge=1800, le=2100),
    league: str = "all",
    qualified: bool | None = None,
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0, le=100_000),
) -> Response:
    """A ranked leaderboard for one stat. Ties share a rank."""
    stats = CATALOGUE[category]
    stat_key = stat or DEFAULT_STAT[category]
    if stat_key not in stats:
        raise _invalid(f"Unknown {category} stat {stat_key!r}. Options: {', '.join(stats)}.")
    s = stats[stat_key]

    meta = await get_meta()
    lo = from_ if from_ is not None else meta["seasons"]["first"]
    hi = to if to is not None else meta["seasons"]["last"]
    if lo > hi:
        raise _invalid("'from' must not be after 'to'.")

    known = {lg["league_id"] for lg in meta["leagues"]}
    if league == "all":
        league_ids = None
    elif league == "negro":
        league_ids = _negro_league_ids(meta)
    elif league in known:
        league_ids = [league]
    else:
        raise _invalid(f"Unknown league {league!r}. Use 'all', 'negro' or a league_id.")
    if scope == "career" and league_ids is not None:
        raise _invalid("League filters apply to single-season leaderboards only.")

    # Rate stats are meaningless for a handful of plate appearances or innings.
    is_qualified = True if s.rate else bool(qualified)

    key = ("leaderboard", category, s.key, scope, lo, hi, league, is_qualified, limit, offset)
    payload = await cached(key, lambda: _build_leaderboard(
        category, s, scope, lo, hi, league, league_ids, is_qualified, limit, offset, meta))
    return json_response(request, payload)


async def _build_leaderboard(category, s, scope, lo, hi, league, league_ids, is_qualified,
                             limit, offset, meta) -> dict:
    split = league_ids is not None
    table = TABLES[(category, scope, split)]
    I = sql.Identifier  # noqa: E741
    rank_col = I(s.column)
    direction = sql.SQL("ASC" if s.ascending else "DESC")

    # Identity columns, then the supporting stats (plus the ranked one if missing).
    if scope == "season":
        identity = [("season", "Season", "year"), ("team_ids", "Team", "text"), ("league", "Lg", "text")]
        identity_sql = sql.SQL("season, team_ids, {} AS league").format(
            I("league_id" if split else "league_ids"))
        tiebreak = sql.SQL("season, full_name, player_id")
    else:
        identity = [("years", "Years", "text"), ("seasons", "Yrs", "int")]
        identity_sql = sql.SQL("first_season::text || '–' || last_season::text AS years, seasons")
        tiebreak = sql.SQL("full_name, player_id")

    shown = s.display or s.column
    context = list(CONTEXT[category])
    if shown not in [c for c, _, _ in context]:
        context.append((shown, s.label, s.fmt))

    where = [sql.SQL("{} IS NOT NULL").format(rank_col)]
    if scope == "season":
        where.append(sql.SQL("season BETWEEN %(lo)s AND %(hi)s"))
    else:  # careers that overlap the range; totals are still whole careers
        where.append(sql.SQL("first_season <= %(hi)s AND last_season >= %(lo)s"))
    if split:
        where.append(sql.SQL("league_id = ANY(%(leagues)s)"))
    if is_qualified:
        where.append(I(QUALIFIER[(category, scope)]))

    query = sql.SQL(
        "SELECT RANK() OVER (ORDER BY {rank} {dir}) AS rank, count(*) OVER () AS total, "
        "player_id, full_name, {identity}, {context} "
        "FROM {table} WHERE {where} "
        "ORDER BY {rank} {dir}, {tiebreak} "
        "LIMIT %(limit)s OFFSET %(offset)s"
    ).format(
        rank=rank_col, dir=direction, identity=identity_sql,
        context=sql.SQL(", ").join(I(c) for c, _, _ in context),
        table=sql.Identifier("marts", table),
        where=sql.SQL(" AND ").join(where), tiebreak=tiebreak,
    )
    rows = await db.fetch(query, {"lo": lo, "hi": hi, "leagues": league_ids,
                                  "limit": limit, "offset": offset})
    total = rows[0]["total"] if rows else 0
    for r in rows:
        del r["total"]

    columns = [{"key": "rank", "label": "#", "format": "int"},
               {"key": "full_name", "label": "Player", "format": "player"}]
    columns += [{"key": k, "label": label, "format": fmt} for k, label, fmt in identity]
    columns += [{"key": c, "label": label, "format": fmt, "highlight": c == shown}
                for c, label, fmt in context]

    notes = []
    if is_qualified:
        notes.append(QUALIFIER_NOTE[(category, scope)])
    if scope == "career" and (lo, hi) != (meta["seasons"]["first"], meta["seasons"]["last"]):
        notes.append(f"Careers that overlap {lo}–{hi}; totals cover the whole career.")
    if league == "negro":
        notes.append("Negro Leagues: " + ", ".join(league_ids) + ".")

    return {
        "params": {"category": category, "stat": s.key, "scope": scope, "from": lo, "to": hi,
                   "league": league, "qualified": is_qualified, "limit": limit, "offset": offset},
        "stat": s.public(),
        "total": total,
        "columns": columns,
        "rows": rows,
        "notes": notes,
    }
