"""Phase 4: embed player names and nicknames into pgvector for search.

    bgpt-pipeline embed            # after `make transform`

Builds every name a player might be searched by, embeds each one with a
pretrained sentence-transformers model, and writes them to
vectors.player_aliases with an HNSW cosine index. The backend embeds the
search text with the same model and combines nearest neighbours with plain
name matching (see backend/search.py).

Aliases per player:
  name        the Lahman full name                         "Lou Gehrig"
  given_name  given names + last name, when different      "Henry Louis Gehrig"
  nickname    curated seed (staging.seed_player_nicknames) "The Iron Horse"
  name_form   curated suffix forms Lahman leaves out        "Ken Griffey Jr."
  unaccented  any of the above without accents, when different  "Jose Abreu"

The whole table is rebuilt in one transaction, so a failed run leaves the
previous index in place. The model name and dimension are recorded in
vectors._embed_log; the backend only uses vector search when its model matches.
"""

from __future__ import annotations

import logging
import os
import time
import unicodedata
from dataclasses import dataclass

import psycopg
from pgvector.psycopg import register_vector

from .config import DATABASE_URL

log = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
SCHEMA = "vectors"
TABLE = "player_aliases"


class EmbedError(Exception):
    """The inputs for embedding are missing (run `make transform` first)."""


@dataclass(frozen=True)
class Alias:
    player_id: str
    alias: str
    kind: str


def strip_accents(text: str) -> str:
    """'José Abreu' -> 'Jose Abreu'. Leaves text without accents unchanged."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def build_aliases(players: list[tuple], nicknames: list[tuple]) -> list[Alias]:
    """Every distinct (player, alias) pair, case-insensitively, first kind wins.

    players:   (player_id, full_name, name_last, name_given)
    nicknames: (player_id, alias, kind)
    """
    seen: set[tuple[str, str]] = set()
    out: list[Alias] = []

    def add(player_id: str, alias: str | None, kind: str) -> None:
        alias = " ".join((alias or "").split())
        if not alias:
            return
        key = (player_id, alias.casefold())
        if key in seen:
            return
        seen.add(key)
        out.append(Alias(player_id, alias, kind))
        plain = strip_accents(alias)
        if plain != alias:
            add(player_id, plain, "unaccented")

    for player_id, full_name, name_last, name_given in players:
        add(player_id, full_name, "name")
        if name_given and name_last:
            add(player_id, f"{name_given} {name_last}", "given_name")
    for player_id, alias, kind in nicknames:
        add(player_id, alias, kind)
    return out


def _read_inputs(conn: psycopg.Connection) -> tuple[list[tuple], list[tuple]]:
    try:
        players = conn.execute(
            "SELECT player_id, full_name, name_last, name_given FROM marts.players "
            "WHERE is_player ORDER BY player_id"
        ).fetchall()
        nicknames = conn.execute(
            "SELECT player_id, alias, kind FROM staging.seed_player_nicknames ORDER BY player_id, alias"
        ).fetchall()
    except psycopg.errors.UndefinedTable as e:
        raise EmbedError(f"{e.diag.message_primary}; run `make transform` first") from None
    if not players:
        raise EmbedError("marts.players is empty; run `make build` first")
    return players, nicknames


def embed(database_url: str | None = None, model_name: str = DEFAULT_MODEL, batch_size: int = 512) -> int:
    """Rebuild vectors.player_aliases. Returns the number of aliases written."""
    from sentence_transformers import SentenceTransformer  # heavy import; only when embedding

    url = database_url or DATABASE_URL
    with psycopg.connect(url) as conn:
        players, nicknames = _read_inputs(conn)
    aliases = build_aliases(players, nicknames)
    log.info("built %d aliases for %d players (%d curated)", len(aliases), len(players), len(nicknames))

    started = time.monotonic()
    log.info("loading %s", model_name)
    model = SentenceTransformer(model_name, device="cpu")
    # Renamed in sentence-transformers 6; keep working with older versions.
    dim = (getattr(model, "get_embedding_dimension", None) or model.get_sentence_embedding_dimension)()
    vectors = model.encode([a.alias for a in aliases], batch_size=batch_size,
                           normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
    encode_seconds = time.monotonic() - started
    log.info("embedded %d aliases (%d dims) in %.1fs", len(aliases), dim, encode_seconds)

    with psycopg.connect(url) as conn, conn.transaction():
        register_vector(conn)
        conn.execute(f"DROP TABLE IF EXISTS {SCHEMA}.{TABLE}")
        conn.execute(f"""
            CREATE TABLE {SCHEMA}.{TABLE} (
                alias_id   serial PRIMARY KEY,
                player_id  text NOT NULL,
                alias      text NOT NULL,
                kind       text NOT NULL,
                embedding  vector({dim}) NOT NULL
            )""")
        with conn.cursor().copy(
            f"COPY {SCHEMA}.{TABLE} (player_id, alias, kind, embedding) FROM STDIN WITH (FORMAT BINARY)"
        ) as copy:
            copy.set_types(["text", "text", "text", "vector"])
            for a, v in zip(aliases, vectors):
                copy.write_row((a.player_id, a.alias, a.kind, v))
        # Build the indexes after loading: much faster than maintaining them row by row.
        conn.execute(f"CREATE INDEX ON {SCHEMA}.{TABLE} USING hnsw (embedding vector_cosine_ops)")
        conn.execute(f"CREATE INDEX ON {SCHEMA}.{TABLE} (player_id)")
        # Trigram index for spelling-tolerant matching ("Mickey Mantel"), which a
        # pretrained sentence model is weak at. pg_trgm is a trusted extension.
        conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        conn.execute(f"CREATE INDEX ON {SCHEMA}.{TABLE} USING gin (alias gin_trgm_ops)")
        conn.execute(f"""COMMENT ON TABLE {SCHEMA}.{TABLE} IS
            'Searchable names per player (Lahman names, given names, curated nicknames, unaccented forms) '
            'with {model_name} embeddings ({dim} dims, normalized). Built by bgpt-pipeline embed.'""")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA}._embed_log (
                built_at   timestamptz NOT NULL DEFAULT now(),
                model      text NOT NULL,
                dim        int NOT NULL,
                aliases    int NOT NULL,
                players    int NOT NULL,
                nicknames  int NOT NULL,
                seconds    numeric NOT NULL
            )""")
        conn.execute(
            f"INSERT INTO {SCHEMA}._embed_log (model, dim, aliases, players, nicknames, seconds) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (model_name, dim, len(aliases), len(players), len(nicknames), round(encode_seconds, 1)),
        )
        conn.execute(f"ANALYZE {SCHEMA}.{TABLE}")
    log.info("wrote %s.%s", SCHEMA, TABLE)
    return len(aliases)
