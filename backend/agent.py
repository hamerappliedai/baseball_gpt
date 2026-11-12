"""The baseball agent: Claude answers questions by querying the warehouse.

A manual tool-use loop (rather than the SDK's beta tool runner) because the
backend relays its own event stream to the browser: text as it is generated,
plus each query Claude runs and how many rows came back.

    run_turn(client, messages) -> async iterator of event dicts:
        {"type": "text", "text": ...}
        {"type": "query", "id": ..., "purpose": ..., "sql": ...}
        {"type": "query_result", "id": ..., "rows": n, "truncated": bool, "error": str|None}
        {"type": "error", "message": ...}
        {"type": "done", "stop_reason": ...}
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

import anthropic

import db
from schema import schema_prompt

log = logging.getLogger("baseball_gpt.agent")

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MAX_TOKENS = int(os.environ.get("CLAUDE_MAX_TOKENS", "64000"))
EFFORT = os.environ.get("CLAUDE_EFFORT", "medium")  # low | medium | high | xhigh | max
# After this many rounds of queries, Claude must answer with what it has.
MAX_TOOL_ROUNDS = int(os.environ.get("MAX_TOOL_ROUNDS", "8"))
# Retries when a streamed tool input is unparseable JSON (rare).
MAX_JSON_RETRIES = 2

SQL_TOOL: dict[str, Any] = {
    "name": "run_sql",
    "description": (
        "Run one read-only PostgreSQL SELECT against the baseball warehouse and get the rows "
        "back as a pipe-separated table. Only the tables described in the system prompt exist. "
        f"At most {db.MAX_ROWS} rows are returned, so aggregate or ORDER BY ... LIMIT in SQL "
        f"rather than fetching everything. Queries time out after {db.STATEMENT_TIMEOUT_MS // 1000}s. "
        "On an error, read the message, fix the query and try again."
    ),
    "eager_input_streaming": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "purpose": {
                "type": "string",
                "description": "A few words saying what this query finds, shown to the user "
                "(e.g. 'Find Babe Ruth's player_id', 'Top 10 single-season HR').",
            },
            "query": {"type": "string", "description": "A single SELECT (or WITH ... SELECT) statement."},
        },
        "required": ["purpose", "query"],
        "additionalProperties": False,
    },
}

INSTRUCTIONS = """\
You are Baseball GPT, an analyst who answers questions about baseball history from the SABR \
Lahman Baseball Database (major league statistics 1871-2025, including the Negro Leagues \
1920-1950). You answer by querying a PostgreSQL warehouse with the run_sql tool.

How to answer:
- Every statistic, record, date or fact you state must come from a query you ran in this \
conversation. Do not answer from memory, even when you are confident: the database is the \
source of truth, and where it differs from what you remember, report the database and say \
the sources differ.
- Resolve people to player_id first (search players by full_name, name_last or name_given \
with ILIKE, and use first_season/last_season/teams to pick the right one when names repeat), \
then filter every other table by player_id.
- Use the table built for the question: *_seasons for a player's season totals, \
*_league_seasons for league leaders, *_careers for career totals, team_seasons for team \
records, postseason_* for the postseason.
- For single-season rate leaderboards (AVG, OBP, SLG, OPS, ERA, WHIP), filter on \
qualifies_batting_title / qualifies_era_title; for career rate leaderboards, on \
qualifies_career_leaders. Say which threshold you used. If short or unusual seasons \
(19th century, Negro Leagues, independent clubs) dominate a leaderboard, say so, and offer \
a modern-era or minimum-PA version.
- Prefer one well-built query over many small ones. If a query fails, fix it and retry.
- If the data can't answer the question (the database has no pitch-level data, no \
salaries outside 1985-2016, nothing after the 2025 season), say so plainly.

How to reply:
- Lead with the answer, then the supporting numbers. Use a Markdown table for lists of more \
than three rows. Keep it concise; don't narrate your queries (the user sees them).
- Mention the seasons, league and qualification rule behind a number when they matter.

# Database schema
"""


def _validate_tool_input(raw: Any) -> tuple[str, str] | None:
    """Return (purpose, query) when the input matches the schema, else None.

    With eager input streaming the API doesn't validate tool input, and the
    SDK's tolerant parser can hand back a truncated object, so check it here.
    """
    if not isinstance(raw, dict) or set(raw) - {"purpose", "query"}:
        return None
    query, purpose = raw.get("query"), raw.get("purpose", "")
    if not isinstance(query, str) or not query.strip() or not isinstance(purpose, str):
        return None
    return purpose.strip(), query.strip()


def _content_for_history(content: list[Any]) -> list[Any]:
    """Assistant content to append to the history.

    After a mid-output refusal fallback the API requires dropping thinking and
    tool_use blocks that precede the last `fallback` block (keeping the
    fallback block itself in place). Without a fallback this is a no-op.
    """
    boundary = max((i for i, b in enumerate(content) if b.type == "fallback"), default=-1)
    if boundary < 0:
        return list(content)
    drop = {"thinking", "redacted_thinking", "tool_use"}
    return [b for i, b in enumerate(content) if i >= boundary or b.type not in drop]


async def _system_blocks() -> list[dict[str, Any]]:
    # One stable block, cached: instructions + schema never change within a process.
    return [{"type": "text", "text": INSTRUCTIONS + await schema_prompt(),
             "cache_control": {"type": "ephemeral"}}]


async def run_turn(client: anthropic.AsyncAnthropic, messages: list[dict[str, Any]]) -> AsyncIterator[dict]:
    """Answer the latest user message, querying the database as needed."""
    messages = list(messages)
    system = await _system_blocks()
    rounds = 0
    json_retries = 0
    wrote_text = False

    while True:
        params: dict[str, Any] = dict(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=[SQL_TOOL],
            messages=messages,
            output_config={"effort": EFFORT},
            # Cache the growing conversation too, so each loop round re-reads it cheaply.
            cache_control={"type": "ephemeral"},
            # If a safety classifier declines, the API re-runs the request on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        if rounds >= MAX_TOOL_ROUNDS:
            params["tool_choice"] = {"type": "none"}  # answer with what you have

        new_block = True
        try:
            async with client.beta.messages.stream(**params) as stream:
                async for event in stream:
                    if event.type == "content_block_start":
                        new_block = True
                    elif event.type == "text":
                        if new_block and wrote_text:
                            yield {"type": "text", "text": "\n\n"}  # separate text blocks
                        new_block = False
                        wrote_text = True
                        yield {"type": "text", "text": event.text}
                final = await stream.get_final_message()
            json_retries = 0
        except ValueError:
            # Streamed tool input the SDK couldn't parse at all; no tool_use_id to
            # answer, so re-issue the turn (bounded). API errors aren't ValueError.
            json_retries += 1
            if json_retries > MAX_JSON_RETRIES:
                raise
            log.warning("unparseable tool input, retrying turn")
            continue

        if final.stop_reason == "refusal":
            yield {"type": "error", "message": "Claude declined to answer this request."}
            yield {"type": "done", "stop_reason": final.stop_reason}
            return

        if final.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": _content_for_history(final.content)})
            continue

        content = _content_for_history(final.content)
        tool_uses = [b for b in content if b.type == "tool_use"]
        if not tool_uses:
            if final.stop_reason == "max_tokens":
                yield {"type": "error", "message": "Reply was cut off (max_tokens reached)."}
            yield {"type": "done", "stop_reason": final.stop_reason}
            return
        if final.stop_reason == "max_tokens":
            # A truncated tool input can parse as a valid partial object; don't run it.
            yield {"type": "error", "message": "Reply was cut off mid-query (max_tokens reached)."}
            yield {"type": "done", "stop_reason": final.stop_reason}
            return

        rounds += 1
        results = []
        for block in tool_uses:
            checked = _validate_tool_input(block.input) if block.name == SQL_TOOL["name"] else None
            if checked is None:
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": f"Invalid input for {block.name}: expected "
                                           '{"purpose": string, "query": string}. Try again.'})
                continue
            purpose, query = checked
            yield {"type": "query", "id": block.id, "purpose": purpose, "sql": query}
            try:
                result = await db.run_query(query)
            except db.QueryError as e:
                yield {"type": "query_result", "id": block.id, "rows": 0, "truncated": False, "error": str(e)}
                results.append({"type": "tool_result", "tool_use_id": block.id, "is_error": True,
                                "content": f"Query failed: {e}"})
                continue
            yield {"type": "query_result", "id": block.id, "rows": len(result.rows),
                   "truncated": result.truncated, "error": None}
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": result.to_text()})

        # All results for one assistant turn go back in a single user message.
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": results})
