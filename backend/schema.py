"""Describe the marts schema to Claude, from the database itself.

dbt writes every mart table and column description into Postgres as COMMENTs
(persist_docs), so the database is the single source of truth: this reads the
catalog and renders it compactly. A column that has the same description in
every table it appears in (player_id, hr, era, ...) is defined once in a
glossary instead of once per table, which roughly halves the prompt.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from db import open_pool

SCHEMA = "marts"

_CATALOG_SQL = """
SELECT c.relname,
       obj_description(c.oid, 'pg_class')            AS table_comment,
       a.attname,
       format_type(a.atttypid, a.atttypmod)          AS type,
       col_description(c.oid, a.attnum)              AS column_comment
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
WHERE n.nspname = %s AND c.relkind IN ('r', 'v', 'm')
ORDER BY c.relname, a.attnum
"""

# Postgres type names shortened for the prompt.
_TYPE_ALIASES = {
    "integer": "int",
    "bigint": "bigint",
    "numeric": "numeric",
    "text": "text",
    "boolean": "bool",
    "date": "date",
    "character varying": "text",
}


@dataclass
class Column:
    name: str
    type: str
    comment: str | None


@dataclass
class Table:
    name: str
    comment: str | None
    columns: list[Column]


async def load_tables() -> list[Table]:
    pool = await open_pool()
    async with pool.connection() as conn:
        rows = await (await conn.execute(_CATALOG_SQL, (SCHEMA,))).fetchall()
    tables: dict[str, Table] = {}
    for relname, table_comment, col, typ, col_comment in rows:
        t = tables.setdefault(relname, Table(relname, table_comment, []))
        t.columns.append(Column(col, _TYPE_ALIASES.get(typ, typ), col_comment))
    return list(tables.values())


def render(tables: list[Table]) -> str:
    """Render tables as compact text: a shared glossary, then one block per table."""
    # Columns whose description is identical everywhere they appear go in the glossary.
    descs: dict[str, set[str | None]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for t in tables:
        for c in t.columns:
            descs[c.name].add(c.comment)
            counts[c.name] += 1
    glossary = {
        name: next(iter(d))
        for name, d in descs.items()
        if counts[name] > 1 and len(d) == 1 and next(iter(d))
    }

    out = [f"All tables are in the `{SCHEMA}` schema (it is on the search_path; no prefix needed)."]
    out.append("\n## Common columns (same meaning in every table that has them)")
    out += [f"- {name}: {desc}" for name, desc in sorted(glossary.items())]
    for t in tables:
        out.append(f"\n## {t.name}")
        if t.comment:
            out.append(t.comment)
        cols = []
        for c in t.columns:
            if c.name in glossary or not c.comment:
                cols.append(f"- {c.name} {c.type}")
            else:
                cols.append(f"- {c.name} {c.type}: {c.comment}")
        out += cols
    return "\n".join(out)


_cached: str | None = None


async def schema_prompt(refresh: bool = False) -> str:
    """The rendered schema, cached for the life of the process (rebuild the
    marts and restart the backend to pick up changes)."""
    global _cached
    if _cached is None or refresh:
        tables = await load_tables()
        if not tables:
            raise RuntimeError(f"No tables in schema {SCHEMA!r}. Run `make build` first.")
        _cached = render(tables)
    return _cached
