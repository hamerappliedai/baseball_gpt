"""Hybrid player search over vectors.player_aliases (phase 4).

Three signals, combined in one SQL query:

  name match   exact or prefix match on any alias or on the last name.
               These win outright, ordered by games played, so "robinson"
               and "babe" behave the way people expect.
  spelling     pg_trgm word similarity, for typos ("mickey mantel").
  meaning      cosine similarity of sentence-transformers embeddings, for
               nicknames and loose phrasing ("iron horse", "hammering hank").

Everything that isn't an exact or prefix match is ranked by spelling +
meaning (+0.5 if the text appears inside an alias). Embedding-only hits need
a similarity of at least VECTOR_MIN so junk input ("zzzz") returns nothing.

The query is embedded with the same model the pipeline used (checked against
vectors._embed_log). If the model or the table isn't available, players.py
falls back to plain SQL name matching.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import os
import time
from typing import Any

import db

log = logging.getLogger("baseball_gpt.search")

EMBED_MODEL = os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
VECTOR_MIN = float(os.environ.get("SEARCH_VECTOR_MIN", "0.65"))  # embedding-only hits
FUZZY_MIN = float(os.environ.get("SEARCH_FUZZY_MIN", "0.45"))    # trigram-only hits
KNN = 50
RECHECK_SECONDS = 60

_model = None
_model_lock = asyncio.Lock()
_ready: bool | None = None
_ready_checked = 0.0


def _load_model():
    from sentence_transformers import SentenceTransformer  # heavy; import on first use

    try:  # use the cached copy without touching the network when we can
        return SentenceTransformer(EMBED_MODEL, device="cpu", local_files_only=True)
    except Exception:  # noqa: BLE001 - not cached yet
        return SentenceTransformer(EMBED_MODEL, device="cpu")


async def _get_model():
    global _model
    if _model is None:
        async with _model_lock:
            if _model is None:
                started = time.monotonic()
                _model = await asyncio.to_thread(_load_model)
                log.info("loaded %s in %.1fs", EMBED_MODEL, time.monotonic() - started)
    return _model


@functools.lru_cache(maxsize=2048)
def _encode(text: str) -> str:
    """The query as a pgvector literal; cached because typeahead repeats itself."""
    vec = _model.encode([text], normalize_embeddings=True, convert_to_numpy=True)[0]
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def embed_query(text: str) -> str:
    await _get_model()
    return await asyncio.to_thread(_encode, text)


async def vectors_ready() -> bool:
    """True when the alias table exists and was built with our model.

    A negative answer is rechecked every RECHECK_SECONDS, so running
    `bgpt-pipeline embed` turns hybrid search on without a restart.
    """
    global _ready, _ready_checked
    if _ready or (_ready is False and time.monotonic() - _ready_checked < RECHECK_SECONDS):
        return bool(_ready)
    _ready_checked = time.monotonic()
    try:
        rows = await db.fetch("SELECT model FROM vectors._embed_log ORDER BY built_at DESC LIMIT 1")
        built_with = rows[0]["model"] if rows else None
        _ready = built_with == EMBED_MODEL
        if not _ready:
            log.warning("vector search off: index built with %r, backend uses %r", built_with, EMBED_MODEL)
    except Exception as e:  # noqa: BLE001 - table missing, no privilege: fall back quietly
        log.warning("vector search off: %s", e)
        _ready = False
    return _ready


async def warm_up() -> None:
    """Load the model in the background at startup so the first search is fast."""
    try:
        if await vectors_ready():
            await embed_query("warm up")
    except Exception:  # noqa: BLE001
        log.exception("search warm-up failed; searches will fall back to SQL")


def like_escape(s: str) -> str:
    """Escape LIKE wildcards so user input only ever matches literally."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


_HYBRID_SQL = f"""
WITH knn AS (
    SELECT alias_id FROM vectors.player_aliases
    ORDER BY embedding <=> %(vec)s::vector LIMIT {KNN}
),
fuzzy AS (
    SELECT alias_id FROM vectors.player_aliases WHERE %(text)s <%% alias
),
lexical AS (
    SELECT alias_id FROM vectors.player_aliases WHERE alias ILIKE %(anywhere)s
),
candidates AS (
    SELECT a.player_id, a.alias, a.kind,
           1 - (a.embedding <=> %(vec)s::vector) AS vec,
           word_similarity(%(text)s, a.alias) AS fuzz,
           CASE WHEN lower(a.alias) = %(exact)s OR lower(p.name_last) = %(exact)s THEN 0
                WHEN a.alias ILIKE %(prefix)s OR p.name_last ILIKE %(prefix)s THEN 1
                WHEN a.alias ILIKE %(anywhere)s THEN 2
           END AS tier
    FROM vectors.player_aliases a
    JOIN marts.players p USING (player_id)
    WHERE a.alias_id IN (SELECT alias_id FROM knn UNION SELECT alias_id FROM fuzzy
                         UNION SELECT alias_id FROM lexical)
),
scored AS (
    SELECT *, fuzz + vec + CASE WHEN tier = 2 THEN 0.5 ELSE 0 END AS score
    FROM candidates
    WHERE tier IS NOT NULL OR fuzz >= %(fuzzy_min)s OR vec >= %(vector_min)s
),
best AS (  -- one row per player: its best-matching alias
    SELECT DISTINCT ON (player_id) *
    FROM scored
    ORDER BY player_id, tier NULLS LAST, score DESC
)
SELECT p.player_id, p.full_name, p.first_season, p.last_season, p.primary_position, p.teams,
       p.is_hall_of_famer, p.played_negro_leagues,
       b.alias AS matched_alias, b.kind AS matched_kind, b.tier,
       round(b.vec::numeric, 3) AS vec, round(b.fuzz::numeric, 3) AS fuzz
FROM best b
JOIN marts.players p USING (player_id)
-- When the text is exactly some alias ("Lou Gehrig", "Big Papi"), the user knows
-- who they want: keep name matches and drop the loose similarity-only ones.
WHERE b.tier IS NOT NULL OR NOT EXISTS (SELECT 1 FROM best x WHERE lower(x.alias) = %(exact)s)
ORDER BY CASE WHEN b.tier <= 1 THEN b.tier ELSE 2 END,
         CASE WHEN b.tier <= 1 THEN p.games_played END DESC NULLS LAST,
         b.score DESC, p.games_played DESC NULLS LAST, p.player_id
LIMIT %(limit)s
"""


def _describe(row: dict[str, Any]) -> dict[str, Any]:
    """Say how a result matched, for the UI: by name, by an alias, or by similarity."""
    tier, kind, alias = row.pop("tier"), row.pop("matched_kind"), row.pop("matched_alias")
    row.pop("vec"), row.pop("fuzz")
    if tier is None:
        row["match"] = "similar"
    else:
        row["match"] = "name" if kind in ("name", "unaccented") else "alias"
    row["matched_alias"] = alias if kind not in ("name", "unaccented") else None
    return row


async def hybrid_search(text: str, limit: int) -> list[dict[str, Any]]:
    vec = await embed_query(text)
    esc = like_escape(text)
    params = {
        "vec": vec, "text": text, "exact": text.lower(), "prefix": f"{esc}%",
        "anywhere": f"%{esc}%", "fuzzy_min": FUZZY_MIN, "vector_min": VECTOR_MIN, "limit": limit,
    }
    results = await db.fetch_many({
        # Settings for this transaction only: the reader's search_path is just
        # marts, but pgvector's type and operators and pg_trgm's functions live
        # in public; the trigram threshold the GIN index filters on; and a wider
        # HNSW search for better recall.
        "settings": "SELECT set_config('search_path', 'marts, public', true), "
                    "set_config('pg_trgm.word_similarity_threshold', %(fuzzy)s, true), "
                    "set_config('hnsw.ef_search', '100', true)",
        "rows": _HYBRID_SQL,
    }, {**params, "fuzzy": str(FUZZY_MIN)})
    return [_describe(r) for r in results["rows"]]
