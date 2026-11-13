"""The tool-use loop, driven by a scripted fake Claude client (no API calls)."""

from types import SimpleNamespace as NS

import pytest

import agent
import db

pytestmark = pytest.mark.anyio


def text(t):
    return NS(type="text", text=t)


def tool_use(id_, query, purpose="look something up", name="run_sql"):
    return NS(type="tool_use", id=id_, name=name, input={"purpose": purpose, "query": query})


def reply(*content, stop_reason=None):
    if stop_reason is None:
        stop_reason = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
    return NS(content=list(content), stop_reason=stop_reason)


class FakeStream:
    def __init__(self, final):
        self.final = final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def __aiter__(self):
        for block in self.final.content:
            yield NS(type="content_block_start")
            if block.type == "text":
                yield NS(type="text", text=block.text)

    async def get_final_message(self):
        return self.final


class FakeClient:
    """Returns the scripted replies in order and records every request."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests = []
        self.beta = NS(messages=NS(stream=self._stream))

    def _stream(self, **params):
        # Snapshot messages: the agent keeps appending to the same list.
        self.requests.append({**params, "messages": list(params["messages"])})
        return FakeStream(self.replies.pop(0))


@pytest.fixture(autouse=True)
def fake_schema(monkeypatch):
    async def schema_prompt():
        return "## players\n- player_id text"
    monkeypatch.setattr(agent, "schema_prompt", schema_prompt)


@pytest.fixture
def queries(monkeypatch):
    """Replace the database with canned results; records the SQL it was given."""
    seen = []

    async def run_query(sql):
        seen.append(sql)
        if "boom" in sql:
            raise db.QueryError('column "boom" does not exist')
        return db.QueryResult(["hr"], [(714,)], False)

    monkeypatch.setattr(db, "run_query", run_query)
    return seen


async def collect(client, question="How many HR did Babe Ruth hit?"):
    return [e async for e in agent.run_turn(client, [{"role": "user", "content": question}])]


async def test_runs_query_and_answers(queries):
    client = FakeClient(
        reply(text("Let me check."), tool_use("t1", "SELECT hr FROM batting_careers")),
        reply(text("Babe Ruth hit **714** home runs.")),
    )
    events = await collect(client)

    assert queries == ["SELECT hr FROM batting_careers"]
    kinds = [e["type"] for e in events]
    assert kinds == ["text", "query", "query_result", "text", "text", "done"]
    assert events[1] == {"type": "query", "id": "t1", "purpose": "look something up",
                         "sql": "SELECT hr FROM batting_careers"}
    assert events[2]["rows"] == 1 and events[2]["error"] is None
    assert events[3]["text"] == "\n\n"  # separates text from successive blocks
    assert "".join(e["text"] for e in events if e["type"] == "text").endswith("**714** home runs.")

    # The second request carries the assistant turn and the tool result.
    second = client.requests[1]["messages"]
    assert second[-2]["role"] == "assistant"
    result = second[-1]["content"][0]
    assert result["tool_use_id"] == "t1" and "714" in result["content"] and "is_error" not in result


async def test_request_shape():
    client = FakeClient(reply(text("Hi")))
    await collect(client)
    req = client.requests[0]
    assert req["model"] == agent.MODEL
    assert req["tools"][0]["name"] == "run_sql" and req["tools"][0]["eager_input_streaming"]
    assert req["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "## players" in req["system"][0]["text"]
    # Claude's own knowledge is allowed only in the labeled background blockquote.
    assert f"begins with {agent.BACKGROUND_LABEL}" in req["system"][0]["text"]
    assert req["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in req["betas"]
    assert "tool_choice" not in req


async def test_query_errors_go_back_to_claude(queries):
    client = FakeClient(
        reply(tool_use("t1", "SELECT boom FROM players")),
        reply(tool_use("t2", "SELECT hr FROM batting_careers")),
        reply(text("714.")),
    )
    events = await collect(client)
    failed = next(e for e in events if e["type"] == "query_result" and e["id"] == "t1")
    assert "boom" in failed["error"]
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Query failed" in result["content"]
    assert events[-1]["type"] == "done"


async def test_invalid_tool_input_is_not_executed(queries):
    bad = NS(type="tool_use", id="t1", name="run_sql", input={"purpose": "x"})  # no query
    client = FakeClient(reply(bad), reply(text("Sorry.")))
    events = await collect(client)
    assert queries == []
    assert not any(e["type"] == "query" for e in events)
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "Invalid input" in result["content"]


async def test_parallel_tool_calls_return_in_one_message(queries):
    client = FakeClient(
        reply(tool_use("a", "SELECT 1"), tool_use("b", "SELECT 2")),
        reply(text("Done.")),
    )
    await collect(client)
    results = client.requests[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"]


async def test_tool_rounds_are_capped(queries, monkeypatch):
    monkeypatch.setattr(agent, "MAX_TOOL_ROUNDS", 2)
    client = FakeClient(
        reply(tool_use("a", "SELECT 1")),
        reply(tool_use("b", "SELECT 2")),
        reply(text("Here's what I found.")),
    )
    await collect(client)
    assert "tool_choice" not in client.requests[1]
    assert client.requests[2]["tool_choice"] == {"type": "none"}


async def test_refusal_stops_without_running_tools(queries):
    client = FakeClient(reply(tool_use("a", "SELECT 1"), stop_reason="refusal"))
    events = await collect(client)
    assert queries == []
    assert events[-2]["type"] == "error" and events[-1] == {"type": "done", "stop_reason": "refusal"}


async def test_truncated_tool_input_is_not_run(queries):
    client = FakeClient(reply(tool_use("a", "SELECT hr FROM bat"), stop_reason="max_tokens"))
    events = await collect(client)
    assert queries == []
    assert "cut off" in events[-2]["message"]


def test_history_drops_pre_fallback_thinking_and_tool_use():
    content = [NS(type="thinking"), NS(type="text"), NS(type="tool_use"),
               NS(type="fallback"), NS(type="thinking"), NS(type="tool_use")]
    kept = [b.type for b in agent._content_for_history(content)]
    assert kept == ["text", "fallback", "thinking", "tool_use"]


@pytest.mark.parametrize("raw,ok", [
    ({"purpose": "p", "query": "SELECT 1"}, True),
    ({"query": "SELECT 1"}, True),
    ({"purpose": "p"}, False),
    ({"purpose": "p", "query": "  "}, False),
    ({"purpose": "p", "query": "SELECT 1", "extra": 1}, False),
    ("SELECT 1", False),
])
def test_validate_tool_input(raw, ok):
    assert (agent._validate_tool_input(raw) is not None) is ok
